import mock
import os
import sys
from shelljob import proc
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/..')

# pep8: ignore=E402
from app import app  # noqa
from app import utils  # noqa
from tests import base  # noqa


class IpamAppTest(base.FlaskTest):

    def setUp(self):
        super(IpamAppTest, self).setUp()
        self.spcall = mock.patch.object(proc, 'call',
                                        return_value=("", 0)).start()
        self.utils_get_next_id_mock = mock.patch.object(utils, "get_next_id",
                                                        return_value=1).start()
        app.testing = True
        self.ctx = app.app_context()
        self.ctx.push()
        self.client = app.test_client()
        self.addCleanup(mock.patch.stopall)

    def tearDown(self):
        self.ctx.pop()
        super(IpamAppTest, self).tearDown()

    def test_get_index(self):
        r, s, h = self.get('/')
        self.assertEqual(s, 200)

    def test_get_not_found(self):
        r, s, h = self.get('/foobar/is/not/there')
        self.assertEqual(s, 404)

    def test_create_subnet_invalid_subnet(self):
        r, s, h = self.post('/subnets', data={})
        self.assertEqual(s, 400)

        # missing value
        r, s, h = self.post('/subnets', data={'cidr': ""})
        self.assertEqual(s, 400)

        # bad value
        r, s, h = self.post('/subnets', data={'cidr': "1.1.1."})
        self.assertEqual(s, 400)
        r, s, h = self.post('/subnets', data={'cidr': "2001:tb8::"})
        self.assertEqual(s, 400)
        self.assertFalse(self.spcall.called)

    def test_create_subnet_family4(self):
        r, s, h = self.post('/subnets', data={'cidr': "1.1.1.1/24"})
        self.assertEqual(s, 200)
        self.assertEqual(r.get("cidr"), "1.1.1.1/24")
        self.assertEqual(r.get("family"), "4")
        self.assertEqual(r.get("subnet_id"), "1")
        self.assertTrue(self.spcall.called)

    def test_create_subnet_family6(self):
        r, s, h = self.post('/subnets', data={'cidr': "2001:eb8::/64"})
        self.assertEqual(s, 200)
        self.assertEqual(r.get("cidr"), "2001:eb8::/64")
        self.assertEqual(r.get("family"), "6")
        self.assertEqual(r.get("subnet_id"), "1")
        self.assertTrue(self.spcall.called)
