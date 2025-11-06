import tempfile
import zipfile
from unittest import mock
from django.contrib.auth.models import Group
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from mcserver.models import (
    User, Session, Trial, Result, Subject
)

# Helper classes
class UserSetupMixin:
    def setUpUsers(self):
        self.owner = User.objects.create_user(username='owner', password='pw')
        self.owner.otp_verified = True
        self.owner.save()

        self.admin = User.objects.create_user(username='admin', password='pw')
        admin_group = Group.objects.create(name='admin')
        self.admin.groups.add(admin_group)

        self.backend = User.objects.create_user(username='backend', password='pw')
        backend_group = Group.objects.create(name='backend')
        self.backend.groups.add(backend_group)

        self.other_user = User.objects.create_user(username='other_user', password='pw')
        self.other_user.otp_verified = True
        self.other_user.save()

        self.unverified_user = User.objects.create_user(username='unverified', password='pw')
        self.unverified_user.otp_verified = False
        self.unverified_user.save()

        self.users = {
            'owner': self.owner,
            'admin': self.admin,
            'backend': self.backend,
            'other': self.other_user,
            'unverified': self.unverified_user,
        }

# Tests
class SessionsPermissionsTests(UserSetupMixin, APITestCase):
    def setUp(self):
        self.setUpUsers()
        self.list_url = '/sessions/'
    
    def _setup_session(self, public):
        self.session = Session.objects.create(user=self.owner, public=public)
        self.detail_url = f'/sessions/{self.session.pk}/'

    def test_get_list(self):
        # Test GET /sessions/ (list)
        public_session = Session.objects.create(user=self.owner, public=True)
        private_session = Session.objects.create(user=self.owner, public=False)

        for role in self.users:
            with self.subTest(role=role):
                self.client.force_authenticate(user=self.users[role])
                resp = self.client.get(self.list_url)
                
                self.assertEqual(resp.status_code, 200)
                session_ids = [s['id'] for s in resp.data]
                # Owners should see public and private sessions
                if role == 'owner':
                    self.assertIn(str(public_session.pk), session_ids)
                    self.assertIn(str(private_session.pk), session_ids)
                else:
                    self.assertIn(str(public_session.pk), session_ids)
                    self.assertNotIn(str(private_session.pk), session_ids)

    def test_get_detail(self):
        # Test GET /sessions/<pk>/ (retrieve)
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    resp = self.client.get(self.detail_url)
                    
                    if role in ['owner', 'admin', 'backend']:
                        expected = 200
                    else:
                        if public is True:
                            expected = 200
                        else:
                            expected = 404
                    self.assertEqual(resp.status_code, expected)

    def test_post(self):
        # Test POST /sessions/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    data = { "user": self.owner.pk,
                             "server": '1.1.1.1',
                             "public": public }
                    resp = self.client.post(self.list_url, data)
                    expected = 201 if role in ['owner', 'admin', 'backend', 'other'] else 403
                    self.assertEqual(resp.status_code, expected)

    def test_put(self):
        # Test PUT /sessions/<pk>/ (update)
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    data = { "user": self.owner.pk,
                             "server": '1.1.1.1',
                             "public": public }
                    resp = self.client.put(self.detail_url, data)
                    
                    if public is True:
                        expected = 200 if role in ['owner', 'admin', 'backend'] else 403
                    else:
                        if role == 'owner':
                            expected = 200
                        elif role in ['admin', 'backend', 'other']:
                            expected = 404
                        else:
                            expected = 403
                    self.assertEqual(resp.status_code, expected)

    def test_patch(self):
        # Test PATCH /sessions/<pk>/ (partial_update)
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    data = { "server": '1.1.1.1' }
                    resp = self.client.patch(self.detail_url, data)
                    
                    if public is True:
                        expected = 200 if role in ['owner', 'admin', 'backend'] else 403
                    else:
                        if role == 'owner':
                            expected = 200
                        elif role in ['admin', 'backend', 'other']:
                            expected = 404
                        else:
                            expected = 403
                    self.assertEqual(resp.status_code, expected)

    def test_delete(self):
        # Test DELETE /sessions/<pk>/ (destroy)
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    # Re-create the session for delete, to make sure the object exists
                    self._setup_session(public=public)
                    self.client.force_authenticate(user=self.users[role])
                    resp = self.client.delete(self.detail_url)
                    
                    if public is True:
                        expected = 204 if role in ['owner', 'admin', 'backend'] else 403
                    else:
                        if role == 'owner':
                            expected = 204
                        elif role in ['admin', 'backend', 'other']:
                            expected = 404
                        else:
                            expected = 403
                    self.assertEqual(resp.status_code, expected)

    def test_search_sessions(self):
        # Test GET /sessions/search_sessions/?text=
        for public in [False, True]:
            self._setup_session(public=public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    resp = self.client.get(f'/sessions/search_sessions/?text={str(self.session.id)[:8]}')
                    
                    self.assertEqual(resp.status_code, 200)
                    if role == 'owner':
                        self.assertTrue(any(str(self.session.id) in s['id'] for s in resp.data))
                    else:
                        self.assertFalse(any(str(self.session.id) in s['id'] for s in resp.data))

    def test_calibration(self):
        # Test GET and POST /sessions/<pk>/calibration/
        for public in [False, True]:
            self._setup_session(public)
            trial = Trial.objects.create(session=self.session, name='calibration')
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    get_resp = self.client.get(f'/sessions/{self.session.pk}/calibration/')
                    post_resp = self.client.post(f'/sessions/{self.session.pk}/calibration/', data={ 'calibration_data': 'data' })
                    
                    if role in ['owner', 'admin', 'backend']:
                        self.assertEqual(get_resp.status_code, 200)
                        self.assertEqual(post_resp.status_code, 200)
                    else:
                        self.assertIn(get_resp.status_code, [403, 404])
                        self.assertIn(post_resp.status_code, [403, 404])

    def test_get_n_calibrated_cameras(self):
        # Test GET /sessions/<pk>/get_n_calibrated_cameras/
        for public in [False, True]:
            self._setup_session(public)
            trial = Trial.objects.create(session=self.session, name='calibration')
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    resp = self.client.get(f'/sessions/{self.session.pk}/get_n_calibrated_cameras/')
                    if role in ['owner', 'admin', 'backend']:
                        self.assertEqual(resp.status_code, 200)
                    else:
                        self.assertIn(resp.status_code, [403, 404])

    def test_rename(self):
        # Test POST /sessions/<pk>/rename/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    session = Session.objects.create(user=self.owner, public=public)
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{session.pk}/rename/'
                    data = { "sessionNewName": "session_new_name" }
                    resp = self.client.post(url, data)
                    
                    if role in ['owner', 'admin', 'backend']:
                        expected = 200
                        self.assertEqual(resp.status_code, expected)
                    else:
                        expected = 404 if role == 'other' else 403
                        self.assertEqual(resp.status_code, expected)

    def test_valid(self):
        # Test GET and POST /sessions/valid
        for role in self.users:
            with self.subTest(role=role):
                session_public = Session.objects.create(user=self.owner, public=True)
                trial_public = Trial.objects.create(session=session_public, 
                                                    name='neutral',
                                                    status='done')
                session_private = Session.objects.create(user=self.owner, public=False)
                trial_private = Trial.objects.create(session=session_private, 
                                                     name='neutral',
                                                     status='done')

                self.client.force_authenticate(user=self.users[role])
                resp_get = self.client.get('/sessions/valid/')
                resp_post = self.client.post('/sessions/valid/')

                if role in ['owner', 'admin', 'backend', 'other']:
                    self.assertEqual(resp_get.status_code, 200)
                    self.assertEqual(resp_post.status_code, 200)

                    # Check that the response contains the expected trials for owner
                    session_ids_get = [t['id'] for t in resp_get.data]
                    session_ids_post = [t['id'] for t in resp_post.data]
                    if role == 'owner':
                        self.assertIn(str(session_public.pk), session_ids_get)
                        self.assertIn(str(session_private.pk), session_ids_get)
                        self.assertIn(str(session_public.pk), session_ids_post)
                        self.assertIn(str(session_private.pk), session_ids_post)
                    else:
                        self.assertNotIn(str(session_public.pk), session_ids_get)
                        self.assertNotIn(str(session_private.pk), session_ids_get)
                        self.assertNotIn(str(session_public.pk), session_ids_post)
                        self.assertNotIn(str(session_private.pk), session_ids_post)
                
                else:
                    self.assertEqual(resp_get.status_code, 200)
                    self.assertNotIn(str(session_public.pk), session_ids_get)
                    self.assertNotIn(str(session_private.pk), session_ids_get)

                    self.assertEqual(resp_post.status_code, 403)

    def test_permanent_remove(self):
        # Test POST /sessions/<pk>/permanent_remove/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_session(public=public)
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/permanent_remove/'
                    resp = self.client.post(url)
                    
                    if role == 'owner':
                        expected = 200
                        self.assertEqual(resp.status_code, expected)
                    else:
                        expected = 404 if role in ['admin', 'backend', 'other'] else 403
                        self.assertEqual(resp.status_code, expected)
   
    def test_trash(self):
        # Test POST /sessions/<pk>/trash/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_session(public=public)
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/trash/'
                    resp = self.client.post(url)

                    if role == 'owner':
                        expected = 200
                        self.assertEqual(resp.status_code, expected)
                    else:
                        expected = 404 if role in ['admin', 'backend', 'other'] else 403
                        self.assertEqual(resp.status_code, expected)

    def test_restore(self):
        # Test POST /sessions/<pk>/restore/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_session(public=public)
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/restore/'
                    resp = self.client.post(url)

                    if role == 'owner':
                        expected = 200
                        self.assertEqual(resp.status_code, 200)
                    else:
                        expected = 404 if role in ['admin', 'backend', 'other'] else 403
                        self.assertEqual(resp.status_code, expected)

    def test_new(self):
        # Test GET /sessions/new/
        for role in self.users:
            with self.subTest(role=role):
                self.client.force_authenticate(user=self.users[role])
                resp = self.client.get('/sessions/new/')

                if role in ['owner', 'admin', 'backend', 'other']:
                    self.assertEqual(resp.status_code, 200)
                else:
                    self.assertEqual(resp.status_code, 403)
    
    @mock.patch('mcserver.views.boto3.client')
    def test_get_qr(self, mock_boto_client):
        # Setup mock
        mock_s3 = mock.Mock()
        mock_boto_client.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = 'http://fake-url.com/qr-code'

        # Test GET /sessions/<pk>/get_qr/
        for public in [False, True]:
            session = Session.objects.create(user=self.owner, 
                                             public=public,
                                             qrcode='fake-qr-code-path.png')
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    resp = self.client.get(f'/sessions/{session.pk}/get_qr/')

                    if role == 'owner':
                        self.assertEqual(resp.status_code, 200)
                    else:
                        self.assertIn(resp.status_code, [403, 404])

    def test_new_subject(self):
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/new_subject/'
                    resp = self.client.get(url)
                    
                    if role == 'owner':
                        self.assertEqual(resp.status_code, 200)
                    else:
                        self.assertEqual(resp.status_code, 404)

    def test_status(self):
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/status/'
                    resp = self.client.get(url)
                    self.assertEqual(resp.status_code, 200)

    def test_record(self):
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/record/?name=new_trial_name'
                    resp = self.client.get(url)
                    
                    if role == 'owner':
                        self.assertEqual(resp.status_code, 200)
                    else:
                        self.assertEqual(resp.status_code, 404)
 
    @mock.patch('mcserver.views.downloadAndZipSession')
    def test_download(self, mock_download_and_zip):
        # Test GET /sessions/<pk>/download/
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    # Create a temporary zip file
                    with tempfile.NamedTemporaryFile(suffix='.zip') as tmp_zip:
                        with zipfile.ZipFile(tmp_zip.name, 'w') as zf:
                            zf.writestr('dummy.txt', 'dummy content')
                        tmp_zip.flush()
                        mock_download_and_zip.return_value = tmp_zip.name

                        self.client.force_authenticate(user=self.users[role])
                        resp = self.client.get(f'/sessions/{self.session.pk}/download/')

                        if role in ['other', 'unverified'] and public is False:
                            self.assertEqual(resp.status_code, 404)
                        else:
                            self.assertEqual(resp.status_code, 200)
                            self.assertEqual(resp['Content-Type'], 'application/zip')

    @mock.patch('mcserver.tasks.download_session_archive.delay')
    def test_async_download(self, mock_download_task):
        mock_task = mock.Mock()
        mock_task.id = 'fake-download_session_archive-id'
        mock_download_task.return_value = mock_task

        # Test GET /sessions/<pk>/async_download/
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/async-download/'
                    resp = self.client.get(url)

                    if public is False:
                        if role == 'owner':
                            self.assertEqual(resp.status_code, 200)
                            self.assertEqual(resp.data, {'task_id': 'fake-download_session_archive-id'})
                        else: 
                            self.assertEqual(resp.status_code, 404)
                    else:
                        self.assertEqual(resp.status_code, 200)
                        self.assertEqual(resp.data, {'task_id': 'fake-download_session_archive-id'})

    def test_get_session_permission(self):
        # Test GET /sessions/<pk>/get_session_permission/
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/get_session_permission/'
                    resp = self.client.get(url)
                    self.assertEqual(resp.status_code, 200)

    def test_get_session_settings(self):
        # Test GET /sessions/<pk>/get_session_settings/
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/get_session_settings/'
                    resp = self.client.get(url)

                    if role in ['other', 'unverified'] and public is False:
                        self.assertEqual(resp.status_code, 404)
                    else:
                        self.assertEqual(resp.status_code, 200)

    def test_set_metadata(self):
        # Test GET /sessions/<pk>/set_metadata/
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/set_metadata/'
                    data = {}
                    resp = self.client.get(url, data)

                    if role in ['owner', 'admin', 'backend']:
                        self.assertEqual(resp.status_code, 200)
                    else:
                        expected = 404 if role == 'other' else 403
                        self.assertEqual(resp.status_code, expected)

    def test_set_subject(self):
        # Test GET /sessions/<pk>/set_subject/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_session(public)
                    subject = Subject.objects.create(name='test_subject', 
                                                     user=self.users['owner'])

                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/set_subject/'
                    data = { "subject_id": subject.pk }
                    resp = self.client.get(url, data)

                    if role == 'owner':
                        self.assertEqual(resp.status_code, 200)
                    else:
                        expected = 404 if role in ['admin', 'backend', 'other'] else 403
                        self.assertEqual(resp.status_code, expected)

    def test_stop(self):
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_session(public)
                    trial = Trial.objects.create(session=self.session, name='test_trial')
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/stop/'
                    resp = self.client.get(url)
                    
                    if role in ['owner', 'admin', 'backend']:
                        self.assertEqual(resp.status_code, 200)
                    else:
                        expected = 404 if role == 'other' else 403
                        self.assertEqual(resp.status_code, expected)

    def test_cancel_trial(self):
        for public in [False, True]:
            for role in self.users:
                self._setup_session(public)
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/cancel_trial/'
                    resp = self.client.get(url)
                    
                    if role in ['owner', 'admin', 'backend']:
                        self.assertEqual(resp.status_code, 200)
                    else:
                        expected = 404 if role == 'other' else 403
                        self.assertEqual(resp.status_code, expected)

    def test_calibration_img(self):
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/calibration_img/'
                    resp = self.client.get(url)
                    
                    if public is True:
                        self.assertEqual(resp.status_code, 200)
                    else:
                        if role in ['owner', 'admin', 'backend']:
                            self.assertEqual(resp.status_code, 200)
                        else:
                            self.assertEqual(resp.status_code, 404)

    def test_neutral_img(self):
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/neutral_img/'
                    resp = self.client.get(url)
                    
                    if public is True:
                        self.assertEqual(resp.status_code, 200)
                    else:
                        if role in ['owner', 'admin', 'backend']:
                            self.assertEqual(resp.status_code, 200)
                        else:
                            self.assertEqual(resp.status_code, 404)

    def test_get_session_statuses(self):
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/get_session_statuses/'
                    data = {'status': 'done'}
                    resp = self.client.post(url, data)
                    if role in ['admin', 'backend', 'owner', 'other']:
                        self.assertEqual(resp.status_code, 200)
                    else:
                        self.assertEqual(resp.status_code, 403)

    def test_set_session_status(self):
        for public in [False, True]:
            self._setup_session(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/sessions/{self.session.pk}/set_session_status/'
                    data = { "status": "archived" }
                    resp = self.client.post(url, data)

                    if role in ['admin', 'backend']:
                        self.assertEqual(resp.status_code, 200)
                    else:
                        expected = 403
                        self.assertEqual(resp.status_code, expected)


class TrialsPermissionsTests(UserSetupMixin, APITestCase):
    def setUp(self):
        self.setUpUsers()
        self.list_url = '/trials/'
    
    def _setup_trial(self, public):
        self.session = Session.objects.create(user=self.owner, public=public)
        self.trial = Trial.objects.create(session=self.session)
        self.detail_url = f'/trials/{self.trial.pk}/'

    def test_get_list(self):
        # Test GET /trials/ (list)
        public_session = Session.objects.create(user=self.owner, public=True)
        private_session = Session.objects.create(user=self.owner, public=False)
        public_trial = Trial.objects.create(session=public_session)
        private_trial = Trial.objects.create(session=private_session)

        for role in self.users:
            with self.subTest(role=role):
                self.client.force_authenticate(user=self.users[role])
                resp = self.client.get(self.list_url)
                # Unverified users should get 200 but only see public trials
                if role == 'unverified':
                    self.assertEqual(resp.status_code, 200)
                    trial_ids = [t['id'] for t in resp.data]
                    self.assertIn(str(public_trial.pk), trial_ids)
                    self.assertNotIn(str(private_trial.pk), trial_ids)
                else:
                    self.assertEqual(resp.status_code, 200)

    def test_get_detail(self):
        # Test GET /trials/<pk>/ (retrieve)
        for public in [False, True]:
            self._setup_trial(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    resp = self.client.get(self.detail_url)

                    if role in ['owner', 'admin', 'backend']:
                        expected = 200
                    else:
                        if public is True:
                            expected = 200
                        else:
                            expected = 404
                    self.assertEqual(resp.status_code, expected)

    def test_patch(self):
        # Test PATCH /trials/<pk>/ (partial_update)
        for public in [False, True]:
            self._setup_trial(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    data = { "status": "processing" }
                    resp = self.client.patch(self.detail_url, data)

                    if role in ['owner', 'admin', 'backend']:
                        expected = 200
                    else:
                        if public is True:
                            expected = 403
                        else:
                            expected = 404 if role == 'other' else 403
                    self.assertEqual(resp.status_code, expected)

    def test_delete(self):
        # Test DELETE /trials/<pk>/ (destroy)
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    # Re-create the trial for delete, to make sure the object exists
                    self._setup_trial(public=public)
                    self.client.force_authenticate(user=self.users[role])
                    resp = self.client.delete(self.detail_url)
                    
                    if role in ['owner', 'admin', 'backend']:
                        expected = 204
                    else:
                        if public is True:
                            expected = 403
                        else:
                            expected = 404 if role == 'other' else 403
                    self.assertEqual(resp.status_code, expected)
   
    def test_dequeue(self):
        # Test GET /trials/dequeue/
        # Custom permissions
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_trial(public)
                    self.trial.status = 'stopped'
                    self.trial.save()
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/trials/dequeue/'
                    resp = self.client.get(url)
                    if role in ['admin', 'backend']:
                        expected = 200
                        self.assertEqual(resp.status_code, expected)
                    else:
                        expected = 403
                        self.assertEqual(resp.status_code, expected)

    def test_get_trials_with_status(self):
        # Test GET /trials/get_trials_with_status/?status=stopped
        for public in [False, True]:
            self._setup_trial(public)
            self.trial.status = 'stopped'
            self.trial.save()
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    url = '/trials/get_trials_with_status/?status=stopped'
                    resp = self.client.get(url)
                    if role in ['admin', 'backend']:
                        expected = 200
                        self.assertEqual(resp.status_code, expected)
                        trial_ids = [t['id'] for t in resp.data]
                        self.assertIn(str(self.trial.pk), trial_ids)
                    else:
                        expected = 403
                        self.assertEqual(resp.status_code, expected)

    def test_rename(self):
        # Test POST /trials/<pk>/rename/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_trial(public)
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/trials/{self.trial.pk}/rename/'
                    data = { "trialNewName": "trial_new_name" }
                    resp = self.client.post(url, data)
                    
                    if role in ['owner', 'admin', 'backend']:
                        expected = 200
                        self.assertEqual(resp.status_code, expected)
                        self.assertEqual(resp.data['data']['name'], "trial_new_name")
                    else:
                        expected = 404 if role == 'other' else 403
                        self.assertEqual(resp.status_code, expected)

    def test_permanent_remove(self):
        # Test POST /trials/<pk>/permanent_remove/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_trial(public)
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/trials/{self.trial.pk}/permanent_remove/'
                    resp = self.client.post(url)
                    
                    if role in ['owner', 'admin', 'backend']:
                        expected = 200
                    else:
                        expected = 404 if role == 'other' else 403
                    self.assertEqual(resp.status_code, expected)
    
    def test_trash(self):
        # Test POST /trials/<pk>/trash/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_trial(public)
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/trials/{self.trial.pk}/trash/'
                    resp = self.client.post(url)
                    
                    if role in ['owner', 'admin', 'backend']:
                        expected = 200
                    else:
                        expected = 404 if role == 'other' else 403
                    self.assertEqual(resp.status_code, expected)

    def test_restore(self):
        # Test POST /trials/<pk>/restore/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_trial(public)
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/trials/{self.trial.pk}/restore/'
                    resp = self.client.post(url)
                    
                    if role in ['owner', 'admin', 'backend']:
                        expected = 200
                    else:
                        expected = 404 if role == 'other' else 403
                    self.assertEqual(resp.status_code, expected)
    
    def test_modifyTags(self):
        # Test POST /trials/<pk>/modifyTags/
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self._setup_trial(public)
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/trials/{self.trial.pk}/modifyTags/'
                    data = { "trialNewTags": ["tag1", "tag2"] }
                    resp = self.client.post(url, data)
                    
                    if role in ['owner', 'admin', 'backend']:
                        expected = 200
                    else:
                        expected = 404 if role == 'other' else 403
                    self.assertEqual(resp.status_code, expected)


class ResultsPermissionsTests(UserSetupMixin, APITestCase):
    def setUp(self):
        self.setUpUsers()
        self.list_url = '/results/'

    def _setup_result(self, public):
        self.session = Session.objects.create(user=self.owner, public=public)
        self.trial = Trial.objects.create(session=self.session)
        self.result = Result.objects.create(trial=self.trial, device_id='dev123', tag='tag1')
        self.detail_url = f'/results/{self.result.pk}/'

    def test_get_list(self):
        # Test GET /results/ (list)
        for role in self.users:
            with self.subTest(role=role):
                self.client.force_authenticate(user=self.users[role])
                resp = self.client.get(self.list_url)
                if role in ['owner', 'admin', 'backend', 'other']:
                    self.assertEqual(resp.status_code, 200)
                else:
                    self.assertEqual(resp.status_code, 403)

    def test_get_detail(self):
        # Test GET /results/<pk>/ (retrieve)
        for public in [False, True]:
            self._setup_result(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    resp = self.client.get(self.detail_url)
                    if role in ['owner', 'admin', 'backend']:
                        self.assertEqual(resp.status_code, 200)
                    else:
                        self.assertEqual(resp.status_code, 403)

    def test_post(self):
        # Test POST /results/
        for public in [False, True]:
            self._setup_result(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    data = {
                        "trial": self.trial.pk,
                        "tag": "new_tag",
                        "device_id": "dev999",
                        "media_url": "fakekey"
                    }
                    resp = self.client.post(self.list_url, data)
                    expected = 201 if role in ['owner', 'admin', 'backend'] else 403
                    self.assertEqual(resp.status_code, expected)

    def test_put(self):
        # Test PUT /results/<pk>/ (update)
        for public in [False, True]:
            self._setup_result(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    data = {
                        "trial": self.trial.pk,
                        "tag": "updated_tag",
                        "device_id": "dev123",
                        "media_url": "fakekey"
                    }
                    resp = self.client.put(self.detail_url, data)
                    expected = 200 if role in ['owner', 'admin', 'backend'] else 403
                    self.assertEqual(resp.status_code, expected)

    def test_patch(self):
        # Test PATCH /results/<pk>/ (partial_update)
        for public in [False, True]:
            self._setup_result(public)
            for role in self.users:
                with self.subTest(role=role, public=public):
                    self.client.force_authenticate(user=self.users[role])
                    data = { "tag": "patched_tag" }
                    resp = self.client.patch(self.detail_url, data)
                    expected = 200 if role in ['owner', 'admin', 'backend'] else 403
                    self.assertEqual(resp.status_code, expected)

    def test_delete(self):
        # Test DELETE /results/<pk>/ (destroy)
        for public in [False, True]:
            for role in self.users:
                with self.subTest(role=role, public=public):
                    # Re-create the result for delete, to make sure the object exists
                    self._setup_result(public=public)
                    self.client.force_authenticate(user=self.users[role])
                    resp = self.client.delete(self.detail_url)
                    expected = 204 if role in ['owner', 'admin', 'backend'] else 403
                    self.assertEqual(resp.status_code, expected)


class SubjectPermissionsTests(UserSetupMixin, APITestCase):
    def setUp(self):
        self.setUpUsers()
        self.list_url = '/subjects/'

    def _setup_subject(self):
        self.subject = Subject.objects.create(name='test_subject', user=self.owner)
        self.detail_url = f'/subjects/{self.subject.pk}/'

    def test_get_list(self):
        # Test GET /subjects/ (list)
        self._setup_subject()
        for role in self.users:
            with self.subTest(role=role):
                self.client.force_authenticate(user=self.users[role])
                resp = self.client.get(self.list_url)

                if role in ['owner', 'admin', 'backend', 'other']:
                    self.assertEqual(resp.status_code, 200)

                    if role in ['owner', 'admin', 'backend']:
                        self.assertEqual(len(resp.data['subjects']), 1)
                    else:
                        self.assertEqual(len(resp.data['subjects']), 0)
                else:
                    self.assertEqual(resp.status_code, 403)

    def test_get_detail(self):
        # Test GET /subjects/<pk>/ (retrieve)
        self._setup_subject()
        for role in self.users:
            with self.subTest(role=role):
                self.client.force_authenticate(user=self.users[role])
                resp = self.client.get(self.detail_url)
                if role in ['owner', 'admin', 'backend']:
                    self.assertEqual(resp.status_code, 200)
                elif role == 'other':
                    self.assertEqual(resp.status_code, 404)
                else:
                    self.assertEqual(resp.status_code, 403)
    
    def test_post(self):
        for role in self.users:
            with self.subTest(role=role):
                self.client.force_authenticate(user=self.users[role])
                data = { "name": "new_subject" }
                resp = self.client.post(self.list_url, data)

                if role in ['owner', 'admin', 'backend', 'other']:
                    self.assertEqual(resp.status_code, 201)
                else:
                    self.assertEqual(resp.status_code, 403)

    def test_put(self):
        for role in self.users:
            with self.subTest(role=role):
                self._setup_subject()
                self.client.force_authenticate(user=self.users[role])
                data = { "id": self.subject.pk,
                         "name": 'new_subject_name',
                         "subject_tags": ['one', 'two'] }
                resp = self.client.put(self.detail_url, data)

                if role in ['owner', 'admin', 'backend']:
                    self.assertEqual(resp.status_code, 200)
                elif role == 'other':
                    self.assertEqual(resp.status_code, 404)
                else:
                    self.assertEqual(resp.status_code, 403)

    def test_patch(self):
        for role in self.users:
            with self.subTest(role=role):
                self._setup_subject()
                self.client.force_authenticate(user=self.users[role])
                data = { "id": self.subject.pk,
                         "name": 'new_subject_name',
                         "subject_tags": ['one', 'two'] }
                resp = self.client.patch(self.detail_url, data)

                if role in ['owner', 'admin', 'backend']:
                    self.assertEqual(resp.status_code, 200)
                elif role == 'other':
                    self.assertEqual(resp.status_code, 404)
                else:
                    self.assertEqual(resp.status_code, 403)

    def test_delete(self):
        for role in self.users:
            with self.subTest(role=role):
                self._setup_subject()
                self.client.force_authenticate(user=self.users[role])
                resp = self.client.delete(self.detail_url)

                if role in ['owner', 'admin', 'backend']:
                    self.assertEqual(resp.status_code, 204)
                elif role == 'other':
                    self.assertEqual(resp.status_code, 404)
                else:
                    self.assertEqual(resp.status_code, 403)

    def test_trash(self):
        for role in self.users:
            with self.subTest(role=role):
                self._setup_subject()
                self.client.force_authenticate(user=self.users[role])
                url = f'/subjects/{self.subject.pk}/trash/'
                resp = self.client.post(url)

                if role in ['owner']:
                    self.assertEqual(resp.status_code, 200)
                elif role in ['admin', 'backend', 'other']:
                    self.assertEqual(resp.status_code, 404)
                else:
                    self.assertEqual(resp.status_code, 403)
    
    def test_restore(self):
        for role in self.users:
            with self.subTest(role=role):
                self._setup_subject()
                self.client.force_authenticate(user=self.users[role])
                url = f'/subjects/{self.subject.pk}/restore/'
                resp = self.client.post(url)

                if role in ['owner']:
                    self.assertEqual(resp.status_code, 200)
                elif role in ['admin', 'backend', 'other']:
                    self.assertEqual(resp.status_code, 404)
                else:
                    self.assertEqual(resp.status_code, 403)

    @mock.patch('mcserver.views.downloadAndZipSubject')
    def test_download(self, mock_download_and_zip):
        for role in self.users:
            with self.subTest(role=role):
                # Create a temporary zip file
                with tempfile.NamedTemporaryFile(suffix='.zip') as tmp_zip:
                    with zipfile.ZipFile(tmp_zip.name, 'w') as zf:
                        zf.writestr('dummy.txt', 'dummy content')
                    tmp_zip.flush()
                    mock_download_and_zip.return_value = tmp_zip.name

                    self._setup_subject()
                    self.client.force_authenticate(user=self.users[role])
                    url = f'/subjects/{self.subject.pk}/download/'
                    resp = self.client.get(url)

                    if role == 'owner':
                        self.assertEqual(resp.status_code, 200)
                        self.assertEqual(resp['Content-Type'], 'application/zip')
                    elif role in ['admin', 'backend', 'other']:
                        self.assertEqual(resp.status_code, 404)
                    else:
                        self.assertEqual(resp.status_code, 403)

    @mock.patch('mcserver.tasks.download_subject_archive.delay')
    def test_async_download(self, mock_download_task):
        mock_task = mock.Mock()
        mock_task.id = 'fake-download_subject_archive-id'
        mock_download_task.return_value = mock_task
        # Test GET /subject/<pk>/async-download/
        self._setup_subject()
        for role in self.users:
            with self.subTest(role=role):
                self.client.force_authenticate(user=self.users[role])
                url = f'/subjects/{self.subject.pk}/async-download/'
                resp = self.client.get(url)

                if role == 'owner':
                    self.assertEqual(resp.status_code, 200)
                    self.assertEqual(resp.data, {'task_id': 'fake-download_subject_archive-id'})
                elif role in ['admin', 'backend', 'other']:
                    self.assertEqual(resp.status_code, 404)
                else:
                    self.assertEqual(resp.status_code, 403)

    def test_permanent_remove(self):
        for role in self.users:
            with self.subTest(role=role):
                self._setup_subject()
                self.client.force_authenticate(user=self.users[role])
                url = f'/subjects/{self.subject.pk}/permanent_remove/'
                resp = self.client.post(url)

                if role == 'owner':
                    self.assertEqual(resp.status_code, 200)
                elif role in ['admin', 'backend', 'other']:
                    self.assertEqual(resp.status_code, 404)
                else:
                    self.assertEqual(resp.status_code, 403)
