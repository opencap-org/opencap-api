from unittest import mock
from uuid import uuid4

from django.core.files.base import ContentFile
from django.test import TestCase

from mcserver.models import (
    Video, Result, Session, DownloadLog, Trial, User,
    delete_s3_file,
)


class TestDeleteS3File(TestCase):
    """Unit tests for the delete_s3_file helper function."""

    def test_delete_s3_file_with_none(self):
        """delete_s3_file should silently ignore None."""
        result = delete_s3_file(None)
        self.assertIsNone(result)

    def test_delete_s3_file_with_empty_name(self):
        """delete_s3_file should ignore file fields with empty name."""
        mock_file = mock.MagicMock()
        mock_file.name = ''
        result = delete_s3_file(mock_file)
        self.assertIsNone(result)
        mock_file.delete.assert_not_called()

    def test_delete_s3_file_success(self):
        """delete_s3_file should call delete(save=False) on the file field."""
        mock_file = mock.MagicMock()
        mock_file.name = 'test/file.txt'

        delete_s3_file(mock_file)

        mock_file.delete.assert_called_once_with(save=False)

    def test_delete_s3_file_handles_exception(self):
        """delete_s3_file should catch and log exceptions."""
        mock_file = mock.MagicMock()
        mock_file.name = 'test/file.txt'
        mock_file.delete.side_effect = Exception("S3 connection error")

        with mock.patch('builtins.print') as mock_print:
            delete_s3_file(mock_file)

            mock_print.assert_called_once_with(
                "Error deleting file 'test/file.txt': S3 connection error"
            )


class TestS3FileDeletionIntegration(TestCase):
    """Integration tests for S3 file deletion via model .delete() methods."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )

        self.session = Session.objects.create(
            user=self.user,
            public=True
        )

        self.trial = Trial.objects.create(
            session=self.session,
            name='test_trial',
            status='done'
        )

    @mock.patch('mcserver.models.delete_s3_file')
    def test_video_delete_calls_delete_s3_file_three_times(self, mock_delete_s3_file):
        """When a Video is deleted, delete_s3_file should be called for video, video_thumb, and keypoints."""
        video = Video.objects.create(
            trial=self.trial,
            device_id=uuid4()
        )

        video.video.save(
            'test_video.mp4',
            ContentFile(b'video')
        )
        video.video_thumb.save(
            'test_thumb.jpg',
            ContentFile(b'thumb')
        )
        video.keypoints.save(
            'test_keypoints.json',
            ContentFile(b'keypoints')
        )

        video.delete()

        deleted_files = [
            c.args[0].name
            for c in mock_delete_s3_file.call_args_list
        ]

        for expected in [
            video.video.name,
            video.video_thumb.name,
            video.keypoints.name,
        ]:
            self.assertIn(expected, deleted_files)

        self.assertEqual(mock_delete_s3_file.call_count, 3)

    @mock.patch('mcserver.models.delete_s3_file')
    def test_result_delete_calls_delete_s3_file(self, mock_delete_s3_file):
        """When a Result is deleted, delete_s3_file should be called for media."""
        result = Result.objects.create(
            trial=self.trial,
            device_id=uuid4(),
            tag='test_result'
        )

        result.media.save(
            'test_result.mp4',
            ContentFile(b'result')
        )

        result.delete()

        deleted_files = [
            c.args[0].name
            for c in mock_delete_s3_file.call_args_list
        ]

        self.assertIn(result.media.name, deleted_files)
        self.assertEqual(mock_delete_s3_file.call_count, 1)

    @mock.patch('mcserver.models.delete_s3_file')
    def test_session_delete_calls_delete_s3_file(self, mock_delete_s3_file):
        """When a Session is deleted, delete_s3_file should be called for qrcode."""
        session = Session.objects.create(
            user=self.user,
            public=True
        )

        session.qrcode.save(
            'qrcode_test.png',
            ContentFile(b'qrcode')
        )

        session.delete()

        deleted_files = [
            c.args[0].name
            for c in mock_delete_s3_file.call_args_list
        ]

        self.assertIn(session.qrcode.name, deleted_files)
        self.assertEqual(mock_delete_s3_file.call_count, 1)

    @mock.patch('mcserver.models.delete_s3_file')
    def test_download_log_delete_calls_delete_s3_file(self, mock_delete_s3_file):
        """When a DownloadLog is deleted, delete_s3_file should be called for media."""
        download_log = DownloadLog.objects.create(
            task_id='test-task-789',
            user=self.user
        )

        download_log.media.save(
            'test_archive.zip',
            ContentFile(b'archive')
        )

        download_log.delete()

        deleted_files = [
            c.args[0].name
            for c in mock_delete_s3_file.call_args_list
        ]

        self.assertIn(download_log.media.name, deleted_files)
        self.assertEqual(mock_delete_s3_file.call_count, 1)

    @mock.patch('mcserver.models.delete_s3_file')
    def test_result_reset_deletes_media_by_tag(self, mock_delete_s3_file):
        """Result.reset() should delete results by tag and clean up their media files."""
        results = []

        for i in range(3):
            result = Result.objects.create(
                trial=self.trial,
                device_id=uuid4(),
                tag='bulk_test'
            )

            result.media.save(
                f'media_{i}.mp4',
                ContentFile(b'test media')
            )

            results.append(result)

        mock_delete_s3_file.reset_mock()

        Result.reset(trial=self.trial, tag='bulk_test')

        deleted_files = [
            c.args[0].name
            for c in mock_delete_s3_file.call_args_list
        ]

        for result in results:
            self.assertIn(result.media.name, deleted_files)

        self.assertEqual(mock_delete_s3_file.call_count, len(results))


    @mock.patch('mcserver.models.delete_s3_file')
    def test_trial_delete_cascades_cleanup(self, mock_delete_s3_file):
        """Deleting a Trial should cascade to Videos and Results, cleaning up all files."""
        # Create trial
        trial = Trial.objects.create(
            session=self.session,
            name='trial_to_delete',
            status='done'
        )

        # Create video with all fields
        video = Video.objects.create(
            trial=trial,
            device_id=uuid4()
        )
        video.video.save(
            'video1.mp4',
            ContentFile(b'video')
        )

        video.video_thumb.save(
            'thumb1.jpg',
            ContentFile(b'thumb')
        )

        video.keypoints.save(
            'kp1.json',
            ContentFile(b'keypoints')
        )

        # Create result with media
        result = Result.objects.create(
            trial=trial,
            device_id=uuid4(),
            tag='result1'
        )

        result.media.save(
            'result1.mp4',
            ContentFile(b'result')
        )

        # Reset mock to start fresh
        mock_delete_s3_file.reset_mock()

        # Delete the trial - should cascade to video and result
        trial.delete()

        # Verify all files were cleaned up
        deleted_files = [
            c.args[0].name
            for c in mock_delete_s3_file.call_args_list
        ]

        for expected in [
            video.video.name,
            video.video_thumb.name,
            video.keypoints.name,
            result.media.name,
        ]:
            self.assertIn(expected, deleted_files)

        self.assertEqual(mock_delete_s3_file.call_count, 4)