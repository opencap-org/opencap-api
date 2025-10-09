import os
import json
import requests
import time
from http import HTTPStatus
from django.conf import settings
from django.core.files import File
from django.core.files.base import ContentFile
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

from mcserver.models import (
    DownloadLog,
    Session,
    Result,
    Trial,
    AnalysisFunction,
    AnalysisResult,
    AnalysisResultState,
    AnalysisDashboardTemplate,
    AnalysisDashboard,
)
from mcserver.zipsession_v2 import (
    SessionDirectoryConstructor,
    SubjectDirectoryConstructor,
    zipdir
)


@shared_task
def cleanup_trashed_sessions():
    from .models import Session
    now = timezone.now()
    Session.objects.filter(
        trashed=True,
        trashed_at__lt=now-timedelta(days=settings.TRASHED_OBJECTS_CLEANUP_DAYS)).delete()


@shared_task
def cleanup_trashed_trials():
    from .models import Trial
    now = timezone.now()
    Trial.objects.filter(
        trashed=True,
        trashed_at__lt=now-timedelta(days=settings.TRASHED_OBJECTS_CLEANUP_DAYS)).delete()


@shared_task(bind=True)
def download_session_archive(self, session_id, user_id=None):
    """ This task is responsible for asynchronous session archive download.
        If user_id is None, the public session download occurred.
    """
    import shutil

    session_dir_path = None
    session_zip_path = None

    try:
        session_dir_path = SessionDirectoryConstructor().build(session_id)
        session_zip_path = zipdir(session_dir_path)

        create_download_log(session_zip_path, self.request.id, user_id)
        os_remove_with_retry(session_zip_path)

    except Exception as e:
        # Delete files and send the traceback to Sentry if something went wrong
        if session_dir_path and os.path.isfile(session_dir_path):
            shutil.rmtree(session_dir_path)
        if session_zip_path and os.path.isfile(session_zip_path):
            os.remove(session_zip_path)
        if settings.SENTRY_DSN:
            import sentry_sdk
            sentry_sdk.capture_exception(e)
        else:
            print(e)

@shared_task(bind=True)
def download_subject_archive(self, subject_id, user_id):
    """ This task is responsible for asynchronous subject archive download
    """
    import shutil

    subject_dir_path = None
    subject_zip_path = None

    try:
        subject_dir_path = SubjectDirectoryConstructor().build(subject_id)
        subject_zip_path = zipdir(subject_dir_path)
        with open(subject_zip_path, "rb") as archive:
            log = DownloadLog.objects.create(task_id=str(self.request.id), user_id=user_id)
            log.media.save(os.path.basename(subject_zip_path), archive)
            os.remove(subject_zip_path)
    except Exception as e:
        # Delete files and send the traceback to Sentry if something went wrong
        if subject_dir_path and os.path.isfile(subject_dir_path):
            shutil.rmtree(subject_dir_path)
        if subject_zip_path and os.path.isfile(subject_zip_path):
            os.remove(subject_zip_path)
        if settings.SENTRY_DSN:
            import sentry_sdk
            sentry_sdk.capture_exception(e)
        else:
            print(e)


@shared_task
def cleanup_archives():
    """ This task deletes DownloadLogs and related files
        that older than ARCHIVE_CLEANUP_DAYS
    """
    now = timezone.now()
    for log in DownloadLog.objects.filter(
        created_at__lt=now - timedelta(days=settings.ARCHIVE_CLEANUP_DAYS)
    ):
        log.media.delete(save=False)
        log.delete()


@shared_task
def delete_pingdom_sessions():
    """ This task deletes all Session's related to pingdom user
    """
    Session.objects.filter(user__username="pingdom").delete()


@shared_task(bind=True)
def invoke_aws_lambda_function(self, user_id, function_id, data):
    function = AnalysisFunction.objects.get(id=function_id)
    analysis_result = AnalysisResult(
        task_id=str(self.request.id),
        function=function,
        user_id=user_id,
        data=data,
        state=AnalysisResultState.PENDING
    )
    analysis_result.save()

    try:
        response = requests.post(
            function.url,
            json={'body': json.dumps(data)} if function.local_run else data,  # AWS RIE works different with passing parameters
            headers={'Content-Type': 'application/json; charset=utf-8'}
        )
        function_response = response.json()
        # print(f'function_response={function_response}')

        if function.local_run:
            # AWS RIE support
            function_response = function_response['body']

        analysis_result.status = response.status_code
        analysis_result.state = AnalysisResultState.SUCCESSFULL
        if response.status_code >= HTTPStatus.BAD_REQUEST.value:
            analysis_result.state = AnalysisResultState.FAILED
    except (ValueError, requests.RequestException) as e:
        function_response = {'error': str(e)}
        analysis_result.status = HTTPStatus.INTERNAL_SERVER_ERROR.value
        analysis_result.state = AnalysisResultState.FAILED

    if analysis_result.state == AnalysisResultState.SUCCESSFULL:
        trial = Trial.objects.get(
            name=data['specific_trial_names'][0],
            session_id=data['session_id']
        )

        json_path = f'{trial.id}-{function_id}-analysis_result.json'
        result = Result.objects.get_or_create(trial=trial, tag=f'analysis_function_result:{function.id}')[0]
        result.media.save(
            json_path,
            ContentFile(json.dumps(function_response).encode('utf-8'))
        )

        analysis_result.result = result
    else:
        analysis_result.response = function_response
    analysis_result.save(update_fields=['result', 'status', 'state', 'response'])

    # Crreate analysis dashboard if available
    try:
        AnalysisDashboard.objects.get(user_id=user_id, function_id=function_id)
    except AnalysisDashboard.DoesNotExist:
        dashboard_template = AnalysisDashboardTemplate.objects.filter(function_id=function_id).first()
        if dashboard_template:
            AnalysisDashboard.objects.create(
                title=dashboard_template.title,
                layout=dashboard_template.layout,
                user_id=user_id,
                function_id=function_id,
                template=dashboard_template
            )


@shared_task
def submit_cloudwatch_metrics():
    """ This task submits the number of pending trials to CloudWatch
    """
    from mcserver.utils import submit_number_of_pending_trials_to_cloudwatch
    submit_number_of_pending_trials_to_cloudwatch()

# Helper functions
def create_download_log(zip_path, task_id, user_id, 
                        max_retries=5, backoff=0.1):
    archive = None
    for attempt in range(max_retries):
        try:
            archive = open(zip_path, "rb")
            break

        except (FileNotFoundError, PermissionError, OSError) as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff * (2**attempt))

    if archive is not None:
        with archive:
            log = DownloadLog.objects.create(task_id=task_id, user_id=user_id)
            log.media.save(os.path.basename(zip_path), archive)

def os_remove_with_retry(path, max_retries=5, backoff=0.1):
    """
    os.remove(path) with exponential backoff for robustness in cloud
    """
    for attempt in range(max_retries):
        try:
            os.remove(path)
            return
            
        except FileNotFoundError as e:
            # In case we've made it here, we've made a best effort to delete
            # and it's likely gone.
            if attempt == max_retries - 1:
                return
            time.sleep(backoff * (2**attempt))

        except (PermissionError, OSError) as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(backoff * (2**attempt))

# TODO: temporary disabled - need testing
# @shared_task
# def cleanup_unused_sessions():
#     """ This task deletes all Session's that are not used.
#     """
#     from django.db.models import Q, F, Count
#     from .models import Session

#     if settings.CLEANUP_UNUSED_DATA:
#         now = timezone.now()

#         # Delete sessions that are older than 7 days and have no trials
#         ids_for_delete = Session.objects.annotate(
#             trials_count=Count('trial')).filter(
#             Q(updated_at__lt=now-timedelta(days=7)) &
#             Q(trials_count=0)
#         ).values_list('id', flat=True)[:100]
#         Session.objects.filter(id__in=ids_for_delete).delete()

#         # Delete sessions that are older than 7 days and have only calibration trials with errors
#         ids_for_delete = Session.objects.annotate(
#             trials_count=Count('trial'),
#             trials_calibration_error_count=Count(
#                 'trial',
#                 filter=(
#                     Q(trial__name__exact='calibration') & Q(trial__status__exact='error')))).filter(
#             Q(updated_at__lt=now-timedelta(days=7)) &
#             Q(trials_count=F('trials_calibration_error_count'))).values_list('id', flat=True)[:100]
#         Session.objects.filter(id__in=ids_for_delete).delete()


# @shared_task
# def cleanup_stuck_trials():
#     """ This task deletes all Trial's that are not used.
#     """
#     from .models import Trial

#     if settings.CLEANUP_UNUSED_DATA:
#         now = timezone.now()
#         # Limit to 50 trials to avoid long running queries
#         stuck_trials = Trial.objects.filter(
#             created_at__lt=now-timedelta(days=1),
#             status='recording',
#         )
#         stuck_trials.delete()
