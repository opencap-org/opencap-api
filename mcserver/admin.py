from django.contrib import admin
from django.shortcuts import render, redirect
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from mcserver.models import (
    User,
    Session,
    Trial,
    Video,
    Result,
    ResetPassword,
    Subject,
    DownloadLog,
    AnalysisFunction,
    AnalysisResult,
    AnalysisDashboardTemplate,
    AnalysisDashboard,
    SubjectTags,
    TrialTags
)
from django.contrib.auth.models import Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.contrib.admin.models import LogEntry
from django.db.models import Exists, OuterRef
from datetime import timedelta


#admin.site.unregister(Group)
#admin.site.register(Group, GroupAdmin)


@admin.register(User)
class UserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Extras', {
            'fields': (
                'website',
                'institution',
                'profession',
                'country',
                'reason',
                'newsletter',
                'otp_verified',
                'otp_skip_till',                
                'profile_picture',
                'institutional_use'
            )}),
    )


class TrialInline(admin.TabularInline):
    model = Trial
    extra = 0


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'user', 'subject', 'session_name',
        'public', 'isMono',
        'created_at', 'updated_at', 'server',
        'status', 'status_changed',
        'trashed', 'trashed_at',
    )
    raw_id_fields = ('user', 'subject')
    search_fields = ['id', 'user__username', 'subject__name', 'meta__sessionName', 'trial__name']
    inlines = [TrialInline]
    actions = ['set_subject']

    def session_name(self, obj):
        if obj.meta:
            return obj.meta.get('sessionName', '')
        return ''

    session_name.short_description = 'Session name'

    def set_subject(self, request, queryset):
        from .forms import SubjectSelectForm

        form = SubjectSelectForm()
        if request.method == 'POST' and 'apply' in request.POST:
            form = SubjectSelectForm(request.POST)
            if form.is_valid():
                subject = form.cleaned_data['subject']
                for obj in queryset:
                    obj.subject = subject
                    obj.save()
                self.message_user(request, f'Subject set to {subject}')
                return redirect(request.get_full_path())

        opts = self.model._meta
        context = self.admin_site.each_context(request)
        context.update({
            'opts': opts,
            'form': form,
            'objects': queryset,
        })
        return render(request, 'admin/set_subject.html', context)


class ResultInline(admin.TabularInline):
    model = Result
    extra = 0


@admin.register(Trial)
class TrialAdmin(admin.ModelAdmin):
    search_fields = ['id', 'name', 'session__id', 'session__meta__sessionName']
    list_display = (
        'id',
        'name',
        'session',
        'status',
        'has_lidar_data',
        'created_at', 'updated_at',
        'server', 'git_commit',
        'formatted_duration', 'formatted_count',
        'is_meta_null',
        'trashed', 'trashed_at',
    )
    raw_id_fields = ('session',)
    readonly_fields = ('has_lidar_data',)
    inlines = [ResultInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        lidar_videos = Video.objects.filter(
            trial=OuterRef('pk'),
            parameters__has_lidar_data=True,
        )
        return qs.annotate(_has_lidar_data=Exists(lidar_videos))

    def has_lidar_data(self, obj):
        return obj._has_lidar_data

    has_lidar_data.short_description = 'Lidar'
    has_lidar_data.boolean = True

    def is_meta_null(self, obj):
        return obj.meta is None

    def formatted_duration(self, obj):
        if obj.processed_duration:
            hours, remainder = divmod(int(obj.processed_duration.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            return f"{hours:02}:{minutes:02}:{seconds:02}"
        else:
            return obj.processed_duration

    def formatted_count(self, obj):
        return obj.processed_count

    formatted_duration.short_description = 'duration'
    formatted_count.short_description = 'count'


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'trial', 'tag', 'media',
        'device_id',
        'created_at', 'updated_at')
    search_fields = ['id', 'trial__id', 'trial__name']
    raw_id_fields = ('trial',)


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    search_fields = ['id', 'trial__id', 'trial__name']
    list_display = ('id', 'trial', 'video', 'created_at', 'updated_at')
    raw_id_fields = ('trial',)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    search_fields = ['name', 'user__username']
    list_display = (
        'id',
        'name',
        'user',
        'weight',
        'height',
        'age',
        'birth_year',
        'gender',
        'sex_at_birth',
        'trashed',
        'created_at',
        'updated_at',
    )
    raw_id_fields = ('user',)

@admin.register(SubjectTags)
class SubjectTagsAdmin(admin.ModelAdmin):
    search_fields = ['tag', 'subject__name']
    list_display = (
        'id',
        'tag',
        'subject',
    )

@admin.register(TrialTags)
class TrialTagsAdmin(admin.ModelAdmin):
    search_fields = ['tag', 'trial__name']
    list_display = (
        'id',
        'tag',
        'trial',
    )

@admin.register(ResetPassword)
class ResetPasswordAdmin(admin.ModelAdmin):
    search_field = ['email']
    list_display = ['email', 'id', 'datetime']


@admin.register(LogEntry)
class LogEntryAdmin(admin.ModelAdmin):
    # to have a date-based drilldown navigation in the admin page
    date_hierarchy = 'action_time'

    # to filter the resultes by users, content types and action flags
    list_filter = [
        'user',
        'content_type',
        'action_flag'
    ]

    # when searching the user will be able to search in both object_repr and change_message
    search_fields = [
        'object_repr',
        'change_message'
    ]

    list_display = [
        'action_time',
        'user',
        'content_type',
        'action_flag',
    ]


@admin.register(DownloadLog)
class DownloadLogAdmin(admin.ModelAdmin):
    list_display = ['id', "task_id", "user", "created_at", "updated_at"]
    search_fields = ["task_id"]
    raw_id_fields = ["user"]


@admin.register(AnalysisFunction)
class AnalysisFunctionAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'title', 'description', 'is_active',
        'only_for_users_display',
        'local_run', 'created_at']
    search_fields = ['title']
    raw_id_fields = ['only_for_users']

    def only_for_users_display(self, obj):
        return ", ".join([str(u) for u in obj.only_for_users.all()])


@admin.register(AnalysisResult)
class AnalysisResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'task_id', 'user', 'function', 'status', 'state', "created_at", "updated_at"]
    list_filter = ['function', 'state']
    raw_id_fields = ['user', 'trial', 'result']
    search_fields = ['id', 'task_id']


@admin.register(AnalysisDashboardTemplate)
class AnalysisDashboardTemplateAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'function', 'created_at', 'updated_at']
    search_fields = ['title']


@admin.register(AnalysisDashboard)
class AnalysisDashboardAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'function', 'user', 'template', 'created_at', 'updated_at']
    search_fields = ['title']
    raw_id_fields = ['user', 'template']
