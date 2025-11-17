import json
from rest_framework import serializers
from rest_framework import pagination
from mcserver.models import (
    Session,
    User,
    Video,
    Trial,
    Result,
    Subject,
    AnalysisFunction,
    AnalysisResult,
    AnalysisDashboardTemplate,
    AnalysisDashboard,
    SubjectTags,
    TrialTags
)
from rest_framework.validators import UniqueValidator
from django.db.models import Prefetch, Q
from django.utils.translation import gettext as _


class UserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all(), message=_("email-already_exists"))]
    )
    username = serializers.CharField(
        validators=[UniqueValidator(queryset=User.objects.all(), message=_("username-already_exists"))]
    )
    password = serializers.CharField(min_length=8)

    def create(self, validated_data):
        profile_picture = validated_data.get('profile_picture', None)

        user = User.objects.create_user(validated_data['username'],
                                        validated_data['email'],
                                        validated_data['password'],
                                        first_name=validated_data['first_name'],
                                        last_name=validated_data['last_name'],
                                        institution=validated_data['institution'],
                                        reason=validated_data['reason'],
                                        website=validated_data['website'],
                                        newsletter=validated_data['newsletter'],
                                        profession=validated_data['profession'],
                                        country=validated_data['country'],
                                        profile_picture=profile_picture
                                        )

        return user

    class Meta:
        model = User
        fields = (
            'id', 'username', 'first_name', 'last_name',
            'email', 'password', 'institution',
            'reason', 'website',
            'newsletter', 'profession', 'country', 'profile_picture',
            'institutional_use',
        )


class UserInstitutionalUseSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('institutional_use',)


class UserUpdateSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True,
        validators=[UniqueValidator(queryset=User.objects.all(), message=_("email-already_exists"))]
    )

    def create(self, validated_data):
        user = User.objects.create_user(validated_data['username'],
                                        first_name=validated_data['first_name'],
                                        last_name=validated_data['last_name'],
                                        email=validated_data['email'],
                                        country=validated_data['country'],
                                        institution=validated_data['institution'],
                                        profession=validated_data['profession'],
                                        reason=validated_data['reason'],
                                        website=validated_data['website'],
                                        newsletter=validated_data['newsletter'],
                                        )
        return user

    class Meta:
        model = User
        fields = ('id', 'username', 'first_name', 'last_name', 'email', 'country', 'institution', 'profession', 'reason',
                  'website', 'newsletter')


class ProfilePictureSerializer(serializers.ModelSerializer):
    def create(self, validated_data):
        user = User.objects.create_user(validated_data['username'],
                                        profile_picture=validated_data['profile_picture'],
                                        )
        return user

    class Meta:
        model = User
        fields = ('id', 'username', 'profile_picture')


class ResetPasswordSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
            required=True,
            )

    class Meta:
        model = User
        fields = ('email',)


class NewPasswordSerializer(serializers.ModelSerializer):
    password = serializers.CharField(min_length=20,
                                     required=True)
    token = serializers.CharField(min_length=36,
                                  required=True)

    class Meta:
        model = User
        fields = ('password','token',)


# Serializers define the API representation.
class VideoSerializer(serializers.ModelSerializer):
    video_url = serializers.CharField(max_length=256,
                                      required=False)
    class Meta:
        model = Video
        fields = ['id', 'trial', 'device_id', 'video', 'video_url', 'video_thumb', 'parameters', 'created_at', 'updated_at']


# Serializers define the API representation.
class ResultSerializer(serializers.ModelSerializer):
    media_url = serializers.CharField(max_length=256, required=False)

    class Meta:
        model = Result
        fields = ['id', 'trial', 'tag', 'media', 'media_url', 'meta', 'device_id', 'created_at', 'updated_at']


# Serializers define the API representation.
class TrialSerializer(serializers.ModelSerializer):
    videos = VideoSerializer(source='video_set', many=True)
    results = ResultSerializer(source='result_set', many=True)
    
    class Meta:
        model = Trial
        fields = [
            'id', 'session', 'name', 'status', 'videos',
            'results', 'meta', 'created_at', 'updated_at',
            'server', 'is_docker', 'hostname',
            'processed_duration', 'processed_count',
            'git_commit',
            'trashed', 'trashed_at',
        ]


# Serializers define the API representation.
class SessionSerializer(serializers.ModelSerializer):
    # trials = TrialSerializer(source='trial_set', many=True)
    trials = serializers.SerializerMethodField()  # TrialSerializer(source='trial_set', many=True)
    trials_count = serializers.SerializerMethodField()
    trashed_trials_count = serializers.SerializerMethodField()

    name = serializers.SerializerMethodField('session_name')
    sessionName = serializers.SerializerMethodField('get_sessionName')

    @staticmethod
    def setup_eager_loading(queryset):
        # queryset = queryset.prefetch_related("trial_set").all()
        queryset = queryset.prefetch_related(Prefetch('trial_set', queryset=Trial.objects.order_by('created_at'))).all()

        return queryset

    def get_trials(self, instance):
        trials = instance.trial_set.all()
        return TrialSerializer(trials, many=True).data

    def get_trials_count(self, instance):
        return instance.trial_set.exclude(Q(name='calibration') | Q(~Q(status='done') & Q(name='neutral'))).count()

    def get_trashed_trials_count(self, instance):
        return instance.trial_set.filter(trashed=True).count()

    def session_name(self, session):
        # Get subject name from the latest static trial
        subject_id = None
        if session.subject:
            subject_id = session.subject.name
        elif session.meta is not None and "subject" in session.meta and "id" in session.meta["subject"]:
            subject_id = session.meta["subject"]["id"] 

        # otherwise return session id
        if subject_id:
            return subject_id
        return str(session.id).split("-")[0]

    def get_sessionName(self, session):
        if hasattr(session, 'meta') and session.meta:
            return session.meta.get("sessionName", "")
        return ""

    class Meta:
        model = Session
        fields = [
            'id', 'user', 'public', 'name', 'sessionName',
            'qrcode', 'meta', 'trials', 'server',
            'subject', 'isMono',
            'created_at', 'updated_at',
            'trashed', 'trashed_at', 'trials_count', 'trashed_trials_count',
        ]


class ValidSessionLightSerializer(serializers.ModelSerializer):
    trials = serializers.SerializerMethodField()
    trials_count = serializers.SerializerMethodField()
    trashed_trials_count = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField('session_name')
    sessionName = serializers.SerializerMethodField('get_sessionName')

    class Meta:
        model = Session
        fields = [
            'id', 'user', 'public', 'name', 'sessionName',
            'qrcode', 'meta', 'trials', 'server',
            'subject', 'isMono',
            'created_at', 'updated_at',
            'trashed', 'trashed_at', 'trials_count', 'trashed_trials_count',
        ]

    def get_trials(self, instance):
        return []

    def get_trials_count(self, instance):
        return instance.trial_set.exclude(Q(name='calibration') | Q(~Q(status='done') & Q(name='neutral'))).count()

    def get_trashed_trials_count(self, instance):
        return instance.trial_set.filter(trashed=True).count()

    def session_name(self, session):
        # Get subject name from the latest static trial
        subject_id = None
        if session.subject:
            subject_id = session.subject.name
        elif session.meta is not None and "subject" in session.meta and "id" in session.meta["subject"]:
            subject_id = session.meta["subject"]["id"]

        # otherwise return session id
        if subject_id:
            return subject_id
        return str(session.id).split("-")[0]

    def get_sessionName(self, session):
        if hasattr(session, 'meta') and session.meta:
            return session.meta.get("sessionName", "")
        return ""


class SessionStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = ['status']


class SessionIdSerializer(serializers.ModelSerializer):
    class Meta:
        model = Session
        fields = ['id']


class SessionFilteringSerializer(serializers.Serializer):
    status = serializers.CharField(max_length=64, required=True)
    date_range = serializers.ListField(child=serializers.DateField(), required=False)
    username = serializers.CharField(max_length=64, required=False)


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubjectTags
        fields = [
            'tag',
            'subject',
        ]


class SubjectSerializer(serializers.ModelSerializer):
    sex_display = serializers.SerializerMethodField()
    gender_display = serializers.SerializerMethodField()
    subject_tags = serializers.SerializerMethodField('get_tags')

    class Meta:
        model = Subject
        fields = [
            'id',
            'name',
            'weight',
            'height',
            'age',
            'birth_year',
            'gender', 'gender_display',
            'sex_at_birth', 'sex_display',
            'characteristics',
            # 'sessions',
            'subject_tags',
            'created_at',
            'updated_at',
            'trashed',
            'trashed_at'
        ]

    def create(self, validated_data):
        # Extract subject_tags from validated_data
        subject_tags_data = validated_data.pop('subject_tags', [])

        # Create the subject instance
        subject_instance = Subject.objects.create(**validated_data)

        # Create corresponding tags in SubjectTags table
        for tag_data in subject_tags_data:
            SubjectTags.objects.create(subject=subject_instance, tag=tag_data)

        return subject_instance

    def get_sex_display(self, obj):
        return obj.get_sex_at_birth_display()

    def get_gender_display(self, obj):
        return obj.get_gender_display()

    def get_tags(self, obj):
        return obj.subjecttags_set.all().values_list('tag', flat=True)



class SimpleSubjectSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Subject
        fields = [
            'id',
            'display_name',
        ]

    def get_display_name(self, obj):
        return f'{obj.name} ({obj.weight} Kg, {obj.height} m, {obj.birth_year})'


class NewSubjectSerializer(serializers.ModelSerializer):
    subject_tags = serializers.ListField(write_only=True, required=False)

    class Meta:
        model = Subject
        fields = [
            'name',
            'weight',
            'height',
            'birth_year',
            'gender',
            'sex_at_birth',
            'characteristics',
            'subject_tags',
        ]

    def to_representation(self, instance):
        serializer = SubjectSerializer(instance)
        return serializer.data

    def create(self, validated_data):
        # Extract subject_tags from validated_data
        subject_tags_data = validated_data.pop('subject_tags', [])

        # Create the subject instance
        subject_instance = Subject.objects.create(**validated_data)

        # Insert new tags.
        for tag_data in subject_tags_data:
            SubjectTags.objects.create(subject=subject_instance, tag=tag_data)

        return subject_instance

class SubjectTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubjectTags
        fields = [
            'tag',
            'subject',
        ]

class TrialTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrialTags
        fields = [
            'tag',
            'trial',
        ]

class AnalysisFunctionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisFunction
        fields = ('id', 'title', 'description', 'info')


class AnalysisResultSerializer(serializers.ModelSerializer):
    analysis_function = AnalysisFunctionSerializer(source="function")
    result = ResultSerializer()
    response = serializers.SerializerMethodField()

    class Meta:
        model = AnalysisResult
        fields = ('analysis_function', 'result', 'status', 'state', 'response')
    
    def get_response(self, obj):
        """ Returns Result.media content if analysis was successful,
            otherwise returns the original response with error details.
        """
        if obj.result:
            return json.loads(obj.result.media.read())
        return obj.response


class AnalysisDashboardTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisDashboardTemplate
        fields = ('id', 'title', 'function', 'layout')


class AnalysisDashboardSerializer(serializers.ModelSerializer):

    class Meta:
        model = AnalysisDashboard
        fields = ('id', 'title', 'function', 'template', 'layout')
        
