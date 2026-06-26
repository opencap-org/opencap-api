from unittest import mock
import uuid
from django.test import TestCase

from rest_framework.permissions import IsAuthenticated
from rest_framework.reverse import reverse

from mcserver.models import (
    User, AnalysisFunction, AnalysisResult, AnalysisResultState,
    Session, Trial, Video
)
from mcserver.serializers import (
    AnalysisFunctionSerializer, AnalysisResultSerializer
)
from mcserver.views import AnalysisFunctionsListAPIView


class SerializersTests(TestCase):
    def test_analysis_function_serializer_represents_correct_fields(self):
        self.assertEqual(
            set(AnalysisFunctionSerializer.Meta.fields),
            {'id', 'title', 'description'}
        )
    
    def test_analysis_result_serializer_represents_correct_fields(self):
        self.assertEqual(
            set(AnalysisResultSerializer.Meta.fields),
            {'analysis_function', 'result', 'status', 'state', 'response'}
        )


class ViewsTests(TestCase):
    def setUp(self):
        super().setUp()
        self.function = AnalysisFunction.objects.create(
            title='title 0',
            description='desc 0',
            url='http://localhost:5000/'
        )
        self.user = User.objects.create_user(
            username="johndoe",
            email="johndoe@email.com",
            first_name="John",
            last_name="Dou",
            password="testpass"
        )

    def test_analysis_function_api_view_has_correct_permission_classes(self):
        self.assertEqual(
            AnalysisFunctionsListAPIView.permission_classes, (IsAuthenticated, )
        )
    
    def test_analysis_function_api_view_uses_correct_serializer_class(self):
        self.assertTrue(
            issubclass(
                AnalysisFunctionsListAPIView.serializer_class,
                AnalysisFunctionSerializer
            )
        )

    def test_analysis_function_api_view_list_only_active_functions(self):
        AnalysisFunction.objects.create(
            title='function 0', description='description 0'
        )
        AnalysisFunction.objects.create(
            title='function 1', description='description 1'
        )
        inactive_func = AnalysisFunction.objects.create(
            title='function 2', description='description 2', is_active=False
        )
        view = AnalysisFunctionsListAPIView()
        qs = view.get_queryset()
        self.assertTrue(all(list(qs.values_list('is_active', flat=True))))
    
    @mock.patch('mcserver.views.invoke_aws_lambda_function.delay')
    def test_invoke_analysis_function_endpoint_calls_correct_celery_task_for_func(
        self, mock_celery_task
    ):
        mock_celery_task.return_value = mock.Mock(id='test-task-id')
        data = {'session_id': 'fdffa654-523b-4940-948a-b4178bb3fc65'}
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('analysis-function-invoke', [self.function.id]),
            data=data,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, {'task_id': 'test-task-id'})
        mock_celery_task.assert_called_once_with(
            self.function.id, self.user.id, data
        )
    
    def test_invoke_af_endpoint_responses_404_if_function_does_not_exist(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('analysis-function-invoke', [1000]),
            data={},
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)
    
    def test_invoke_af_endpoint_responses_404_if_function_is_not_active(self):
        function = AnalysisFunction.objects.create(
            title='title 0', description='desc 0', is_active=False
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse('analysis-function-invoke', [function.id]),
            data={},
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

    def test_invoke_af_endpoint_responses_403_if_anon_user_requests(self):
        response = self.client.post(
            reverse('analysis-function-invoke', [self.function.id]),
            data={},
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 403)
    
    def test_analysis_result_on_ready_responses_202_if_result_does_not_exist(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('analysis-result-on-ready', ['dummy']))
        self.assertEqual(response.status_code, 202)
    
    def test_analysis_result_on_ready_responses_202_if_result_is_pending(self):
        result = AnalysisResult.objects.create(
            task_id='task-id',
            user=self.user,
            function=self.function,
            state=AnalysisResultState.PENDING
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse('analysis-result-on-ready', [result.task_id]))
        self.assertEqual(response.status_code, 202)
    
    def test_analysis_result_on_ready_responses_200_if_result_ready(self):
        self.client.force_login(self.user)
        for state in (AnalysisResultState.SUCCESSFULL, AnalysisResultState.FAILED):
            result = AnalysisResult.objects.create(
                task_id=f'task-id-{state}',
                user=self.user,
                function=self.function,
                state=state
            )
            response = self.client.get(
                reverse('analysis-result-on-ready', [result.task_id])
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, AnalysisResultSerializer(result).data)

    def test_session_status_waits_for_video_field_when_not_save_local(self):
        session = Session.objects.create(user=self.user, save_local=False)
        trial = Trial.objects.create(
            session=session, status='stopped', name='walk-fast'
        )
        Video.objects.create(
            trial=trial, device_id=uuid.uuid4(), video='uploaded-a.mov',
            saved_local=True
        )
        pending_video = Video.objects.create(
            trial=trial, device_id=uuid.uuid4(), saved_local=True
        )

        self.client.force_login(self.user)
        response = self.client.get(f'/sessions/{session.pk}/status/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'uploading')
        self.assertEqual(response.data['trialname'], 'walk-fast')
        self.assertEqual(response.data['n_videos_uploaded'], 1)

        pending_video.video = 'uploaded-b.mov'
        pending_video.save(update_fields=['video'])
        response = self.client.get(f'/sessions/{session.pk}/status/')

        self.assertEqual(response.data['status'], 'processing')
        self.assertEqual(response.data['n_videos_uploaded'], 2)

    def test_session_status_waits_for_video_or_saved_local_when_save_local(self):
        session = Session.objects.create(user=self.user, save_local=True)
        trial = Trial.objects.create(
            session=session, status='stopped', name='squat-1'
        )
        Video.objects.create(
            trial=trial, device_id=uuid.uuid4(), video='uploaded-a.mov',
            saved_local=False
        )
        Video.objects.create(
            trial=trial, device_id=uuid.uuid4(), video='', saved_local=True
        )
        pending_video = Video.objects.create(
            trial=trial, device_id=uuid.uuid4(), video='', saved_local=False
        )

        self.client.force_login(self.user)
        response = self.client.get(f'/sessions/{session.pk}/status/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'uploading')
        self.assertEqual(response.data['trialname'], 'squat-1')
        self.assertEqual(response.data['n_videos_uploaded'], 2)

        pending_video.saved_local = True
        pending_video.save(update_fields=['saved_local'])
        response = self.client.get(f'/sessions/{session.pk}/status/')

        self.assertEqual(response.data['status'], 'processing')
        self.assertEqual(response.data['n_videos_uploaded'], 3)
