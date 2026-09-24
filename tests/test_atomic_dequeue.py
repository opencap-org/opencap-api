import threading
from unittest.mock import patch

from django.test import TransactionTestCase
from django.db import connection, transaction
from django.urls import reverse, NoReverseMatch
from rest_framework.test import APIClient

from mcserver.models import Trial, Session
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group


class DequeueConcurrencyTest(TransactionTestCase):
    def setUp(self):
        User = get_user_model()

        # 1. Setup mock data and permissions
        self.user = User.objects.create(
            username="worker_test",
            is_staff=True,
            is_superuser=True
        )

        backend_group, _ = Group.objects.get_or_create(name="backend")
        admin_group, _ = Group.objects.get_or_create(name="admin")
        self.user.groups.add(backend_group, admin_group)

        self.session = Session.objects.create(user=self.user, isMono=False)

        # 2. Create valid trials
        # Trial 1 is created first and should therefore be selected first
        # (as per dequeue's order_by("created_at", "id")).
        # The concurrency test then verifies that Trial 2 is selected when
        # Trial 1 is locked.
        self.trial_1 = Trial.objects.create(
            session=self.session,
            name="calibration",
            status="stopped",
            result=None
        )
        self.trial_2 = Trial.objects.create(
            session=self.session,
            name="calibration",
            status="stopped",
            result=None
        )

        # 3. Dynamically resolve the URL to guarantee we hit the right endpoint
        try:
            self.dequeue_url = reverse('trial-dequeue')
        except NoReverseMatch:
            try:
                self.dequeue_url = reverse('trials-dequeue')
            except NoReverseMatch:
                self.dequeue_url = '/api/trials/dequeue/'

    def test_concurrent_dequeue_skips_locked_rows(self):
        client1 = APIClient()
        client2 = APIClient()

        client1.force_authenticate(user=self.user)
        client2.force_authenticate(user=self.user)

        results = {}
        thread1_locked = threading.Event()
        worker2_done = threading.Event()

        def worker_1():
            original_save = Trial.save

            def delayed_save(self_instance, *args, **kwargs):
                if self_instance.pk == self.trial_1.pk:
                    thread1_locked.set()

                    if not worker2_done.wait(timeout=10):
                        raise AssertionError("Timed out waiting for Worker 2")

                return original_save(self_instance, *args, **kwargs)

            try:
                with patch('mcserver.models.Trial.save', new=delayed_save):
                    response = client1.get(
                        self.dequeue_url,
                        REMOTE_ADDR='127.0.0.1'
                    )

                    if response.status_code == 200:
                        results['worker1'] = response.data.get('id')
                    else:
                        results['worker1_error'] = (
                            f"HTTP {response.status_code}: "
                            f"{response.content.decode('utf-8')[:200]}"
                        )
            except Exception as e:
                results['worker1_error'] = f"Exception: {str(e)}"
            finally:
                connection.close()

        def worker_2():
            try:
                # Worker 1 signals from Trial.save(), which is called only after
                # select_for_update() has acquired the Trial 1 row lock.
                if not thread1_locked.wait(timeout=10):
                    results['worker2_error'] = "Timed out waiting for Worker 1 to acquire the Trial 1 lock"
                    return

                response = client2.get(
                    self.dequeue_url,
                    REMOTE_ADDR='127.0.0.1'
                )

                if response.status_code == 200:
                    results['worker2'] = response.data.get('id')
                else:
                    results['worker2_error'] = (
                        f"HTTP {response.status_code}: "
                        f"{response.content.decode('utf-8')[:200]}"
                    )
            except Exception as e:
                results['worker2_error'] = f"Exception: {str(e)}"
            finally:
                worker2_done.set()
                connection.close()

        t1 = threading.Thread(target=worker_1)
        t2 = threading.Thread(target=worker_2)

        t1.start()
        t2.start()

        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertFalse(t1.is_alive(), "Worker 1 did not finish")
        self.assertFalse(t2.is_alive(), "Worker 2 did not finish")

        # Check results
        self.assertIsNotNone(
            results.get('worker1'),
            f"Worker 1 failed! Reason: {results.get('worker1_error')}"
        )
        self.assertIsNotNone(
            results.get('worker2'),
            f"Worker 2 failed! Reason: {results.get('worker2_error')}"
        )

        # Confirm they grabbed different trials
        self.assertEqual(
            results['worker1'],
            str(self.trial_1.id),
            "Worker 1 did not get Trial 1"
        )

        self.assertEqual(
            results['worker2'],
            str(self.trial_2.id),
            "Worker 2 did not skip locked Trial 1 to get Trial 2"
        )

        # Confirm they updated correctly in the database
        self.trial_1.refresh_from_db()
        self.trial_2.refresh_from_db()
        self.assertEqual(self.trial_1.status, "processing")
        self.assertEqual(self.trial_2.status, "processing")

    def test_dequeue_falls_through_locked_admin_trial(self):
        self.trial_1.delete()
        self.trial_2.delete()

        backend_group, _ = Group.objects.get_or_create(name="backend")
        admin_group, _ = Group.objects.get_or_create(name="admin")

        admin_user = get_user_model().objects.create(
            username="admin_trial_user",
            is_staff=True,
            is_superuser=True,
        )
        admin_user.groups.add(backend_group, admin_group)

        normal_user = get_user_model().objects.create(
            username="normal_trial_user",
            is_staff=True,
            is_superuser=True,
        )
        normal_user.groups.add(backend_group)

        admin_session = Session.objects.create(
            user=admin_user,
            isMono=False,
        )
        normal_session = Session.objects.create(
            user=normal_user,
            isMono=False,
        )

        admin_trial = Trial.objects.create(
            session=admin_session,
            name="calibration",
            status="stopped",
            result=None,
        )
        normal_trial = Trial.objects.create(
            session=normal_session,
            name="calibration",
            status="stopped",
            result=None,
        )

        client2 = APIClient()
        client2.force_authenticate(user=self.user)

        results = {}

        admin_locked = threading.Event()
        worker2_done = threading.Event()

        def worker_1():
            try:
                with transaction.atomic():
                    Trial.objects.select_for_update().get(
                        pk=admin_trial.pk
                    )

                    admin_locked.set()

                    # Hold the lock until Worker 2 has attempted dequeue.
                    if not worker2_done.wait(timeout=10):
                        raise AssertionError("Timed out waiting for Worker 2")
            except Exception as e:
                results["worker1_error"] = f"Exception: {str(e)}"
            finally:
                connection.close()

        def worker_2():
            try:
                if not admin_locked.wait(timeout=10):
                    results["worker2_error"] = (
                        "Timed out waiting for admin trial lock"
                    )
                    return

                response = client2.get(
                    self.dequeue_url,
                    REMOTE_ADDR="127.0.0.1",
                )

                if response.status_code == 200:
                    results["worker2"] = response.data.get("id")
                else:
                    results["worker2_error"] = (
                        f"HTTP {response.status_code}: "
                        f"{response.content.decode('utf-8')[:200]}"
                    )
            except Exception as e:
                results["worker2_error"] = f"Exception: {str(e)}"
            finally:
                worker2_done.set()
                connection.close()

        t1 = threading.Thread(target=worker_1)
        t2 = threading.Thread(target=worker_2)

        t1.start()
        t2.start()

        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertFalse(t1.is_alive(), "Worker 1 did not finish")
        self.assertFalse(t2.is_alive(), "Worker 2 did not finish")

        self.assertIsNotNone(
            results.get("worker2"),
            f"Worker 2 failed! Reason: {results.get('worker2_error')}",
        )

        self.assertEqual(
            results["worker2"],
            str(normal_trial.id),
            "Worker 2 did not fall through to the available normal trial",
        )

        admin_trial.refresh_from_db()
        normal_trial.refresh_from_db()

        self.assertEqual(admin_trial.status, "stopped")
        self.assertEqual(normal_trial.status, "processing")

    def test_dequeue_returns_expected_status_codes(self):
        client = APIClient()
        client.force_authenticate(user=self.user)

        # No eligible trials available (Return 404)
        Trial.objects.all().delete()

        response = client.get(
            self.dequeue_url,
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 404)

        # An eligible trial is available (Return 200)
        Trial.objects.create(
            session=self.session,
            name="calibration",
            status="stopped",
            result=None,
        )

        response = client.get(
            self.dequeue_url,
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 200)

        # An eligible trial exists, but is locked by another worker (First worker locks
        # a trial, while the second tries to get it. Since it is locked, it returns 404.)
        Trial.objects.all().delete()

        locked_trial = Trial.objects.create(
            session=self.session,
            name="calibration",
            status="stopped",
            result=None,
        )

        results = {}
        trial_locked = threading.Event()
        worker2_done = threading.Event()

        def worker_1():
            # This worker should lock the only available trial.
            try:
                with transaction.atomic():
                    Trial.objects.select_for_update().get(
                        pk=locked_trial.pk
                    )

                    trial_locked.set()

                    # Hold the lock until Worker 2 has attempted dequeue.
                    if not worker2_done.wait(timeout=10):
                        raise AssertionError("Timed out waiting for Worker 2")
            except Exception as e:
                results["worker1_error"] = f"Exception: {str(e)}"
            finally:
                connection.close()

        def worker_2():
            # This worker should attempt to get the trial. Since it is locked,
            # and it is the only one available, should return 404.
            try:
                if not trial_locked.wait(timeout=10):
                    results["worker2_error"] = (
                        "Timed out waiting for Worker 1 to acquire the trial lock"
                    )
                    return

                response = client.get(
                    self.dequeue_url,
                    REMOTE_ADDR="127.0.0.1",
                )

                if response.status_code == 404:
                    results["worker2"] = True
                else:
                    results["worker2_error"] = (
                        f"HTTP {response.status_code}: "
                        f"{response.content.decode('utf-8')[:200]}"
                    )
            except Exception as e:
                results["worker2_error"] = f"Exception: {str(e)}"
            finally:
                worker2_done.set()
                connection.close()

        t1 = threading.Thread(target=worker_1)
        t2 = threading.Thread(target=worker_2)

        t1.start()
        t2.start()

        t1.join(timeout=15)
        t2.join(timeout=15)

        self.assertFalse(t1.is_alive(), "Worker 1 did not finish")
        self.assertFalse(t2.is_alive(), "Worker 2 did not finish")

        self.assertIsNone(
            results.get("worker1_error"),
            f"Worker 1 failed! Reason: {results.get('worker1_error')}",
        )
        self.assertTrue(
            results.get("worker2"),
            f"Worker 2 failed! Reason: {results.get('worker2_error')}",
        )
