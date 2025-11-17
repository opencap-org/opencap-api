"""mcserver URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from mcserver.views import (
    SessionViewSet,
    VideoViewSet,
    TrialViewSet,
    ResultViewSet,
    SubjectViewSet,
    SubjectTagViewSet,
    TrialTagViewSet,
    DownloadFileOnReadyAPIView,
    UserCreate,
    UserDelete,
    CustomAuthToken,
    verify,
    set_institutional_use,
    reset_otp_challenge,
    check_otp_verified,
    UserViewSet,
    UserInstitutionalUseView,
    ResetPasswordView,
    NewPasswordView,
    AnalysisFunctionsListAPIView,
    InvokeAnalysisFunctionAPIView,
    AnalysisResultOnReadyAPIView,
    AnalysisFunctionTaskIdAPIView,
    AnalysisFunctionsPendingForTrialsAPIView,
    AnalysisFunctionsStatesForTrialsAPIView,
    AnalysisDashboardViewSet,
    GetUserInfo,
    UserUpdate,
    UpdateProfilePicture
)
from rest_framework import routers, serializers, viewsets
from rest_framework.authtoken.views import obtain_auth_token

from django_otp.forms import OTPAuthenticationForm
from django.http import HttpResponse

from django.conf.urls.static import static
from rest_framework_swagger.views import get_swagger_view
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions
from django.conf import settings

schema_view = get_schema_view(
    openapi.Info(
        title="OpenCap API",
        default_version='v1',),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

router = routers.DefaultRouter()

router.register(r'sessions', SessionViewSet, "session")
router.register(r'videos', VideoViewSet)
router.register(r'trials', TrialViewSet, "trial")
router.register(r'results', ResultViewSet)
router.register(r'subjects', SubjectViewSet, "subject")
router.register(r'subject-tags', SubjectTagViewSet, "subject-tags")
router.register(r'trial-tags', TrialTagViewSet, "trial-tags")
router.register(r'users', UserViewSet)
router.register(r'analysis-dashboards', AnalysisDashboardViewSet, "analysis-dashboard")

urlpatterns = [
#    path('session/', new_session),
    path('', include(router.urls)),
    path("health/", lambda x: HttpResponse("OK"), name="health"),
#    path('session/<id>/status/', status),
    path('login/', CustomAuthToken.as_view()),
    path('verify/', verify),
    path('set-institutional-use/', set_institutional_use),
    path('reset-otp-challenge/', reset_otp_challenge),
    path('check-otp-verified/', check_otp_verified),
    path('admin/', admin.site.urls),
    path('register/', UserCreate.as_view(), name='account-create'),
    path('delete-account/', UserDelete.as_view(), name='account-delete'),
    path('update_profile/', UserUpdate.as_view(), name='update-profile'),
    path('update_profile_picture/', UpdateProfilePicture.as_view(), name='update-profile-picture'),
    path('get_user_info/', GetUserInfo.as_view(), name='get_user_info'),
    path('reset-password/', ResetPasswordView.as_view()),
    path('new-password/', NewPasswordView.as_view()),
    path('user-institutional-use/', UserInstitutionalUseView.as_view()),
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('docs/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redocs/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),

    path(
        'logs/<str:task_id>/on-ready/',
        DownloadFileOnReadyAPIView.as_view(),
        name="logs-on-ready"
    ),
    path(
        'analysis-functions/',
        AnalysisFunctionsListAPIView.as_view(),
        name='analysis-functions-list'
    ),
    path(
        'analysis-functions/<int:pk>/invoke/',
        InvokeAnalysisFunctionAPIView.as_view(),
        name='analysis-function-invoke'
    ),
    path(
        'analysis-functions/<int:pk>/task-for-trial/<str:trial_id>/',
        AnalysisFunctionTaskIdAPIView.as_view(),
        name='analysis-function-task-for-trial'
    ),
    path(
        'analysis-result/<str:task_id>/',
        AnalysisResultOnReadyAPIView.as_view(),
        name='analysis-result-on-ready'
    ),
    path(
        'analysis-results/pending/',
        AnalysisFunctionsPendingForTrialsAPIView.as_view(),
        name='analysis-results-pending-for-trials'
    ),
    path(
        'analysis-results/states/',
        AnalysisFunctionsStatesForTrialsAPIView.as_view(),
        name='analysis-results-statuses-for-trials'
    ),
    path('subject-tags/<int:subject_id>/get_tags_subject/', SubjectTagViewSet.as_view({'get': 'get_tags_subject'}),
         name='get_tags_subject'),
    path('trial-tags/<uuid:trial_id>/get_tags_trial/', TrialTagViewSet.as_view({'get': 'get_tags_trial'}),
         name='get_tags_trial'),

    #    path('accounts/login/', OTPAuthenticationForm.as_view(authentication_form=OTPAuthenticationForm)),
]
