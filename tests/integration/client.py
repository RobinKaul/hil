"""Integration tests for client library"""
from hil.flaskapp import app
from hil.client.base import ClientBase, FailedAPICallException
from hil.errors import BadArgumentError, UnknownSubtypeError
from hil.client.client import Client
from hil.test_common import config_testsuite, config_merge, \
    fresh_database, fail_on_log_warnings, server_init, uuid_pattern, \
    HybridHTTPClient, initial_db
from hil.model import db
from hil import config, deferred

import json
import pytest

from passlib.hash import sha512_crypt

ep = "http://127.0.0.1:8000"
username = "hil_user"
password = "hil_pass1234"

http_client = HybridHTTPClient(endpoint=ep,
                               username=username,
                               password=password)
C = Client(ep, http_client)  # Initializing client library


fail_on_log_warnings = pytest.fixture(fail_on_log_warnings)
fresh_database = pytest.fixture(fresh_database)
server_init = pytest.fixture(server_init)
intial_db = pytest.fixture(initial_db)


@pytest.fixture
def dummy_verify():
    """replace sha512_crypt.verify with something faster (albeit broken).

    The tests in this module mostly use the database auth backend. This was,
    frankly, a mistake. This module pulls in way too much "real" code (as
    opposed to mock objects) in general, and patches to improve the
    situation are welcome.

    In the meantime, this fixture works around a serious consequence of using
    the database backend: doing password hasing is **SLOW** (by design; the
    algorithms are intended to make brute-forcing hard), and we've got
    fixtures where we're going through the request handler tens of times for
    every test (before even hitting the test itself).

    So, this fixture monkey-patches sha512_crypt.verify (the function that
    does the work of checking the password), replacing it with a dummy
    implementation. At the time of writing, this shaves about half an hour
    off of our Travis CI runs.

    Longer term, we should:

    * Not go through the http code when creating database objects (do what
      e.g. initial_db and additional_db do instead).
    * Use the null/mock backends and drivers everywhere we can.
    * Scope this fixture to the Test_user class, which is the only place
      that should need to be using the database backend in the first place.
    """

    @staticmethod
    def dummy(*args, **kwargs):
        """dummy replacement, which just returns True."""
        return True

    old = sha512_crypt.verify
    sha512_crypt.verify = dummy  # override the verify() function
    yield  # Test runs here
    sha512_crypt.verify = old  # restore the old implementaton.


@pytest.fixture
def configure():
    """Configure HIL"""
    config_testsuite()
    config_merge({
        'auth': {
            'require_authentication': 'False',
        },
        'extensions': {
            'hil.ext.switches.mock': '',
            'hil.ext.obm.mock': '',
            'hil.ext.network_allocators.null': None,
            'hil.ext.network_allocators.vlan_pool': '',
        },
        'hil.ext.network_allocators.vlan_pool': {
            'vlans': '1001-1040',
        },
    })
    config.load_extensions()


@pytest.fixture
def database_authentication():
    """setup the config file for using databae authentication.
    This fixture is only used by Test_user class"""
    config_testsuite()
    config_merge({
        'auth': {
            'require_authentication': 'False',
        },
        'extensions': {
            'hil.ext.auth.null': None,
            'hil.ext.auth.database': '',
        },
    })
    config.load_extensions()


@pytest.fixture
def initial_admin():
    with app.app_context():
        from hil.ext.auth.database import User
        db.session.add(User(username, password, is_admin=True))
        db.session.commit()


class Test_ClientBase:
    """Tests client initialization and object_url creation. """

    def test_object_url(self):
        """Test the object_url method."""
        x = ClientBase(ep, 'some_base64_string')
        y = x.object_url('abc', '123', 'xy23z')
        assert y == 'http://127.0.0.1:8000/v0/abc/123/xy23z'


@pytest.mark.usefixtures('fail_on_log_warnings', 'configure', 'fresh_database',
                         'server_init', 'initial_db')
class Test_node:
    """ Tests Node related client calls. """

    def test_list_nodes_free(self):
        """(successful) to list_nodes('free')"""
        assert C.node.list('free') == [
                u'free_node_0', u'free_node_1', u'no_nic_node'
                ]

    def test_list_nodes_all(self):
        """(successful) to list_nodes('all')"""
        assert C.node.list('all') == [
                u'free_node_0', u'free_node_1', u'manhattan_node_0',
                u'manhattan_node_1', u'no_nic_node', u'runway_node_0',
                u'runway_node_1'
                ]

    def test_node_register(self):
        """Test node_register"""
        assert C.node.register("dummy-node-01",
                               "http://obmd.example.com/node/dummy-node-01",
                               "secret",
                               "mock", "dummy", "dummy", "dummy") is None
        with pytest.raises(BadArgumentError):
            C.node.register("dummy-node-02",
                            "http://obmd.example.com/node/dummy-node-02",
                            "secret",
                            # Too few arguments
                            "mock", "dummy", "dummy")
        with pytest.raises(BadArgumentError):
            C.node.register("dummy-node-03",
                            "http://obmd.example.com/node/dummy-node-02",
                            "secret",
                            # Too many arguments
                            "mock", "dummy", "dummy", "dummy", "dummy")
        with pytest.raises(UnknownSubtypeError):
            C.node.register("dummy-node-04",
                            "http://obmd.example.com/node/dummy-node-02",
                            "secret",
                            # Non-existent subtype.
                            "donotexist", "dummy", "dummy", "dummy")

    def test_show_node(self):
        """(successful) to show_node"""
        assert C.node.show('free_node_0') == {
                u'metadata': {},
                u'project': None,
                u'nics': [
                    {
                        u'macaddr': u'Unknown',
                        u'port': None,
                        u'switch': None,
                        u'networks': {}, u'label': u'boot-nic'
                        },
                    {
                        u'macaddr': u'Unknown',
                        u'port': u'free_node_0_port',
                        u'switch': u'stock_switch_0',
                        u'networks': {}, u'label': u'nic-with-port'
                        }
                    ],
                u'name': u'free_node_0'
                }

    def test_show_node_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.show('node-/%]07')

    def test_enable_disable_obm(self):
        """Test enable_obm/disable_obm"""
        # The spec says that these calls should silently no-op if the
        # state doesn't need to change so we call them repeatedly in
        # different orders to verify.
        C.node.disable_obm('free_node_0')

        C.node.enable_obm('free_node_0')
        C.node.enable_obm('free_node_0')

        C.node.disable_obm('free_node_0')
        C.node.disable_obm('free_node_0')
        C.node.disable_obm('free_node_0')

        C.node.enable_obm('free_node_0')

    def test_power_cycle(self):
        """(successful) to node_power_cycle"""
        assert C.node.power_cycle('free_node_0') is None

    def test_power_cycle_force(self):
        """(successful) to node_power_cycle(force=True)"""
        assert C.node.power_cycle('free_node_0', True) is None

    def test_power_cycle_no_force(self):
        """(successful) to node_power_cycle(force=False)"""
        assert C.node.power_cycle('free_node_0', False) is None

    def test_power_cycle_bad_arg(self):
        """error on call to power_cycle with bad argument."""
        with pytest.raises(FailedAPICallException):
            C.node.power_cycle('free_node_0', 'wrong')

    def test_power_cycle_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.power_cycle('node-/%]07', False)

    def test_power_off(self):
        """(successful) to node_power_off"""
        assert C.node.power_off('free_node_0') is None

    def test_power_off_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.power_off('node-/%]07')

    def test_set_bootdev(self):
        """ (successful) to node_set_bootdev """
        assert C.node.set_bootdev("free_node_1", "pxe") is None

    def test_node_add_nic(self):
        """Test removing and then adding a nic."""
        C.node.remove_nic('free_node_1', 'boot-nic')
        assert C.node.add_nic('free_node_1', 'boot-nic', 'aa:bb:cc:dd:ee:ff') \
            is None

    def test_node_add_duplicate_nic(self):
        """Adding a nic twice should fail"""
        C.node.remove_nic('free_node_1', 'boot-nic')
        C.node.add_nic('free_node_1', 'boot-nic', 'aa:bb:cc:dd:ee:ff')
        with pytest.raises(FailedAPICallException):
            C.node.add_nic('free_node_1', 'boot-nic', 'aa:bb:cc:dd:ee:ff')

    def test_nosuch_node_add_nic(self):
        """Adding a nic to a non-existent node should fail."""
        with pytest.raises(FailedAPICallException):
            C.node.add_nic('abcd', 'eth0', 'aa:bb:cc:dd:ee:ff')

    def test_add_nic_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.add_nic('node-/%]08', 'eth0', 'aa:bb:cc:dd:ee:ff')

    def test_remove_nic(self):
        """(successful) call to node_remove_nic"""
        assert C.node.remove_nic('free_node_1', 'boot-nic') is None

    def test_remove_duplicate_nic(self):
        """Removing a nic twice should fail"""
        C.node.remove_nic('free_node_1', 'boot-nic')
        with pytest.raises(FailedAPICallException):
            C.node.remove_nic('free_node_1', 'boot-nic')

    def test_remove_nic_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.remove_nic('node-/%]08', 'boot-nic')

    def test_metadata_set(self):
        """ test for registering metadata from a node """
        assert C.node.metadata_set("free_node_0", "EK", "pk") is None

    def test_metadata_delete(self):
        """ test for deleting metadata from a node """
        with pytest.raises(FailedAPICallException):
            C.node.metadata_delete("free_node", "EK")
        C.node.metadata_set("free_node_0", "EK", "pk")
        assert C.node.metadata_delete("free_node_0", "EK") is None

    def test_node_start_console(self):
        """(successful) call to node_start_console"""
        assert C.node.start_console('manhattan_node_1') is None

    def test_node_start_console_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.start_console('node-/%]01')

    def test_node_show_console(self):
        """various calls to node_show_console"""

        # show console without starting should fail.
        with pytest.raises(FailedAPICallException):
            C.node.show_console('manhattan_node_1')

        C.node.start_console('manhattan_node_1')
        assert C.node.show_console('manhattan_node_1') == 'Some console output'

        C.node.stop_console('manhattan_node_1')
        with pytest.raises(FailedAPICallException):
            C.node.show_console('manhattan_node_1')

    def test_node_show_console_reserved_chars(self):
        """test for cataching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.show_console('node-/%]01')

    def test_node_stop_console(self):
        """(successful) call to node_stop_console"""
        assert C.node.stop_console('manhattan_node_1') is None

    def test_node_stop_console_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.stop_console('node-/%]01')

    def test_node_connect_network(self):
        """(successful) call to node_connect_network"""
        response = C.node.connect_network(
                'manhattan_node_1', 'nic-with-port', 'manhattan_pxe',
                'vlan/native')

        # check that the reponse contains a valid UUID.
        assert uuid_pattern.match(response['status_id'])
        deferred.apply_networking()

    def test_node_connect_network_error(self):
        """Duplicate call to node_connect_network should fail."""
        C.node.connect_network(
            'manhattan_node_1', 'nic-with-port', 'manhattan_pxe',
            'vlan/native')
        deferred.apply_networking()
        with pytest.raises(FailedAPICallException):
            C.node.connect_network(
                'manhattan_node_1', 'nic-with-port', 'manhattan_pxe',
                'vlan/native')
        deferred.apply_networking()

    def test_node_connect_network_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.connect_network('node-/%]01', 'eth0', 'net-01',
                                   'vlan/native')

    def test_node_detach_network(self):
        """(successful) call to node_detach_network"""
        C.node.connect_network(
            'manhattan_node_0', 'nic-with-port', 'manhattan_pxe',
            'vlan/native')
        deferred.apply_networking()
        response = C.node.detach_network(
            'manhattan_node_0', 'nic-with-port', 'manhattan_pxe')
        assert uuid_pattern.match(response['status_id'])
        deferred.apply_networking()

    def test_node_detach_network_error(self):
        """Duplicate call to node_detach_network should fail."""
        C.node.connect_network(
            'manhattan_node_0', 'nic-with-port', 'manhattan_pxe',
            'vlan/native')
        deferred.apply_networking()
        C.node.detach_network(
            'manhattan_node_0', 'nic-with-port', 'manhattan_pxe')
        deferred.apply_networking()
        with pytest.raises(FailedAPICallException):
            C.node.detach_network(
                'manhattan_node_0', 'nic-with-port', 'manhattan_pxe')

    def test_node_detach_network_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.node.detach_network('node-/%]04', 'eth0', 'net-04')


@pytest.mark.usefixtures('fail_on_log_warnings', 'configure', 'fresh_database',
                         'server_init', 'initial_db')
class Test_project:
    """ Tests project related client calls."""

    def test_list_projects(self):
        """ test for getting list of project """
        assert C.project.list() == [u'empty-project', u'manhattan', u'runway']

    def test_list_nodes_inproject(self):
        """ test for getting list of nodes connected to a project. """
        assert C.project.nodes_in('manhattan') == [
            u'manhattan_node_0', u'manhattan_node_1']
        assert C.project.nodes_in('runway') == [
            u'runway_node_0', u'runway_node_1']

    def test_list_nodes_inproject_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.project.nodes_in('pr/%[oj-01')

    def test_list_networks_inproject(self):
        """ test for getting list of networks connected to a project. """
        assert C.project.networks_in('runway') == [
                u'runway_provider', u'runway_pxe']

    def test_list_networks_inproject_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.project.networks_in('pr/%[oj-01')

    def test_project_create(self):
        """ test for creating project. """
        assert C.project.create('dummy-01') is None

    def test_duplicate_project_create(self):
        """ test for catching duplicate name while creating new project. """
        C.project.create('dummy-02')
        with pytest.raises(FailedAPICallException):
            C.project.create('dummy-02')

    def test_project_create_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.project.create('dummy/%[-02')

    def test_project_delete(self):
        """ test for deleting project. """
        C.project.create('dummy-03')
        assert C.project.delete('dummy-03') is None

    def test_error_project_delete(self):
        """ test to capture error condition in project delete. """
        with pytest.raises(FailedAPICallException):
            C.project.delete('dummy-03')

    def test_project_delete_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.project.delete('dummy/%[-03')

    def test_project_connect_detach_node(self):
        """ test for connecting/detaching node to project. """
        C.project.create('proj-04')
        assert C.project.connect('proj-04', 'free_node_0') is None
        # connecting it again should fail
        with pytest.raises(FailedAPICallException):
            C.project.connect('proj-04', 'free_node_0')
        assert C.project.detach('proj-04', 'free_node_0') is None

    def test_project_connect_node_nosuchobject(self):
        """ test for connecting no such node or project """
        C.project.create('proj-06')
        with pytest.raises(FailedAPICallException):
            C.project.connect('proj-06', 'no-such-node')
        with pytest.raises(FailedAPICallException):
            C.project.connect('no-such-project', 'free_node_1')

    def test_project_connect_node_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.project.connect('proj/%[-04', 'free_node_1')

    def test_project_detach_node_nosuchobject(self):
        """ Test for while detaching node from project."""
        C.project.create('proj-08')
        with pytest.raises(FailedAPICallException):
            C.project.detach('proj-08', 'no-such-node')
        with pytest.raises(FailedAPICallException):
            C.project.detach('no-such-project', 'free_node_1')

    def test_project_detach_node_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.project.detach('proj/%]-08', 'free_node_0')


@pytest.mark.usefixtures('fail_on_log_warnings', 'configure', 'fresh_database',
                         'server_init', 'initial_db')
class Test_switch:
    """ Tests switch related client calls."""

    def test_list_switches(self):
        """(successful) call to list_switches"""
        assert C.switch.list() == [u'empty-switch', u'stock_switch_0']

    def test_show_switch(self):
        """(successful) call to show_switch"""
        assert C.switch.show('empty-switch') == {
            u'name': u'empty-switch', u'ports': [],
            u'capabilities': ['nativeless-trunk-mode']}

    def test_show_switch_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.switch.show('dell-/%]-01')

    def test_delete_switch(self):
        """(successful) call to switch_delete"""
        assert C.switch.delete('empty-switch') is None

    def test_delete_switch_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.switch.delete('nexus/%]-01')

    def test_switch_register(self):
        """test various cases of switch register"""
        switchinfo = {
            "type": "http://schema.massopencloud.org/haas/v0/switches/mock",
            "username": "name",
            "password": "asdasd",
            "hostname": "example.com"}
        subtype = "http://schema.massopencloud.org/haas/v0/switches/mock"
        assert C.switch.register('mytestswitch', subtype, switchinfo) is None

    def test_switch_register_fail(self):
        """test various cases of switch register"""
        switchinfo = {
            "type": "http://schema.massopencloud.org/haas/v0/switches/mock",
            "username": "name",
            "password": "asdasd",
            "unknown_keyword": "example.com"}
        subtype = "http://schema.massopencloud.org/haas/v0/switches/mock"
        with pytest.raises(FailedAPICallException):
            C.switch.register('mytestswitch', subtype, switchinfo)


@pytest.mark.usefixtures('fail_on_log_warnings', 'configure', 'fresh_database',
                         'server_init', 'initial_db')
class Test_port:
    """ Tests port related client calls."""

    def test_port_register(self):
        """(successful) call to port_register."""
        assert C.port.register('stock_switch_0', 'gi1/1/1') is None

    def test_port_dupregister(self):
        """Duplicate call to port_register should raise an error."""
        C.port.register('stock_switch_0', 'gi1/1/2')
        with pytest.raises(FailedAPICallException):
            C.port.register('stock_switch_0', 'gi1/1/2')

    def test_port_register_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.port.register('mock-/%[-01', 'gi1/1/1')

    def test_port_delete(self):
        """(successful) call to port_delete"""
        C.port.register('stock_switch_0', 'gi1/1/3')
        assert C.port.delete('stock_switch_0', 'gi1/1/3') is None

    def test_port_delete_error(self):
        """Deleting a port twice should fail with an error."""
        C.port.register('stock_switch_0', 'gi1/1/4')
        C.port.delete('stock_switch_0', 'gi1/1/4')
        with pytest.raises(FailedAPICallException):
            C.port.delete('mstock_switch_0', 'gi1/1/4')

    def test_port_delete_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.port.delete('mock/%]-01', 'gi1/1/4')

    def test_port_connect_nic(self):
        """(successfully) Call port_connect_nic on an existent port"""
        C.port.register('stock_switch_0', 'gi1/1/5')
        assert C.port.connect_nic(
                'stock_switch_0', 'gi1/1/5', 'free_node_0', 'boot-nic'
                ) is None

        # port already connected
        with pytest.raises(FailedAPICallException):
            C.port.connect_nic('mock-01', 'gi1/1/5', 'free_node_1', 'boot-nic')

        # port AND free_node_0 already connected
        with pytest.raises(FailedAPICallException):
            C.port.connect_nic('mock-01', 'gi1/1/5', 'free_node_0', 'boot-nic')

    def test_port_connect_nic_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.port.connect_nic('mock/%]-01', 'gi1/1/6', 'node-09', 'eth0')

    def test_port_detach_nic(self):
        """(succesfully) call port_detach_nic."""
        C.port.register('stock_switch_0', 'gi1/1/7')
        C.port.connect_nic(
            'stock_switch_0', 'gi1/1/7', 'free_node_1', 'boot-nic')
        assert C.port.detach_nic('stock_switch_0', 'gi1/1/7') is None

    def test_port_detach_nic_error(self):
        """port_detach_nic on a port w/ no nic should error."""
        C.port.register('stock_switch_0', 'gi1/1/8')
        with pytest.raises(FailedAPICallException):
            C.port.detach_nic('stock_switch_0', 'gi1/1/8')

    def test_port_detach_nic_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.port.detach_nic('mock/%]-01', 'gi1/1/8')

    def test_show_port(self):
        """Test show_port"""
        # do show port on a port that's not registered yet
        with pytest.raises(FailedAPICallException):
            C.port.show('stock_switch_0', 'gi1/1/8')

        C.port.register('stock_switch_0', 'gi1/1/8')
        assert C.port.show('stock_switch_0', 'gi1/1/8') == {}
        C.port.connect_nic(
            'stock_switch_0', 'gi1/1/8', 'free_node_1', 'boot-nic')
        assert C.port.show('stock_switch_0', 'gi1/1/8') == {
                'node': 'free_node_1',
                'nic': 'boot-nic',
                'networks': {}}

        # do show port on a non-existing switch
        with pytest.raises(FailedAPICallException):
            C.port.show('unknown-switch', 'unknown-port')

    def test_show_port_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.port.show('mock/%]-01', 'gi1/1/8')

    def test_port_revert(self):
        """Revert port should run without error and remove all networks"""
        C.node.connect_network(
            'runway_node_0', 'nic-with-port', 'runway_pxe', 'vlan/native')
        deferred.apply_networking()
        assert C.port.show('stock_switch_0', 'runway_node_0_port') == {
                'node': 'runway_node_0',
                'nic': 'nic-with-port',
                'networks': {'vlan/native': 'runway_pxe'}}
        response = C.port.port_revert('stock_switch_0', 'runway_node_0_port')
        assert uuid_pattern.match(response['status_id'])
        deferred.apply_networking()
        assert C.port.show('stock_switch_0', 'runway_node_0_port') == {
                'node': 'runway_node_0',
                'nic': 'nic-with-port',
                'networks': {}}

    def test_port_revert_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.port.port_revert('mock/%]-01', 'gi1/0/1')


@pytest.mark.usefixtures('fail_on_log_warnings', 'database_authentication',
                         'fresh_database', 'server_init', 'initial_admin',
                         'dummy_verify')
class Test_user:
    """ Tests user related client calls."""

    def test_list_users(self):
        """Test for getting list of user"""
        assert C.user.list() == {
            u'hil_user': {u'is_admin': True, u'projects': []}
        }

    def test_user_create(self):
        """ Test user creation. """
        assert C.user.create('billy', 'pass1234', is_admin=True) is None
        assert C.user.create('bobby', 'pass1234', is_admin=False) is None

    def test_user_create_duplicate(self):
        """ Test duplicate user creation. """
        C.user.create('bill', 'pass1234', is_admin=False)
        with pytest.raises(FailedAPICallException):
            C.user.create('bill', 'pass1234', is_admin=False)

    def test_user_create_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.user.create('b/%]ill', 'pass1234', is_admin=True)

    def test_user_delete(self):
        """ Test user deletion. """
        C.user.create('jack', 'pass1234', is_admin=True)
        assert C.user.delete('jack') is None

    def test_user_delete_error(self):
        """ Test error condition in user deletion. """
        C.user.create('Ata', 'pass1234', is_admin=True)
        C.user.delete('Ata')
        with pytest.raises(FailedAPICallException):
            C.user.delete('Ata')

    def test_user_delete_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.user.delete('A/%]ta')

    def test_user_add(self):
        """ test adding a user to a project. """
        C.project.create('proj-sample')
        C.user.create('Sam', 'pass1234', is_admin=False)
        assert C.user.add('Sam', 'proj-sample') is None

    def test_user_add_error(self):
        """Test error condition while granting user access to a project."""
        C.project.create('test-proj01')
        C.user.create('sam01', 'pass1234', is_admin=False)
        C.user.add('sam01', 'test-proj01')
        with pytest.raises(FailedAPICallException):
            C.user.add('sam01', 'test-proj01')

    def test_user_add_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.user.add('sam/%]01', 'test-proj01')

    def test_user_remove(self):
        """Test revoking user's access to a project. """
        C.project.create('test-proj02')
        C.user.create('sam02', 'pass1234', is_admin=False)
        C.user.add('sam02', 'test-proj02')
        assert C.user.remove('sam02', 'test-proj02') is None

    def test_user_remove_error(self):
        """Test error condition while revoking user access to a project. """
        C.project.create('test-proj03')
        C.user.create('sam03', 'pass1234', is_admin=False)
        C.user.create('xxxx', 'pass1234', is_admin=False)
        C.user.add('sam03', 'test-proj03')
        C.user.remove('sam03', 'test-proj03')
        with pytest.raises(FailedAPICallException):
            C.user.remove('sam03', 'test_proj03')

    def test_user_remove_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.user.remove('sam/%]03', 'test-proj03')

    def test_user_set_admin(self):
        """Test changing a user's admin status """
        C.user.create('jimmy', '12345', is_admin=False)
        C.user.create('jimbo', '678910', is_admin=True)
        assert C.user.set_admin('jimmy', True) is None
        assert C.user.set_admin('jimbo', False) is None

    def test_user_set_admin_demote_error(self):
        """Tests error condition while editing a user who doesn't exist. """
        C.user.create('gary', '12345', is_admin=True)
        C.user.delete('gary')
        with pytest.raises(FailedAPICallException):
            C.user.set_admin('gary', False)

    def test_user_set_admin_promote_error(self):
        """Tests error condition while editing a user who doesn't exist. """
        C.user.create('hugo', '12345', is_admin=False)
        C.user.delete('hugo')
        with pytest.raises(FailedAPICallException):
            C.user.set_admin('hugo', True)

    def test_user_set_admin_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.user.set_admin('hugo/%]', True)


@pytest.mark.usefixtures('fail_on_log_warnings', 'configure', 'fresh_database',
                         'server_init', 'initial_db')
class Test_network:
    """ Tests network related client calls. """

    def test_network_list(self):
        """ Test list of networks. """
        assert C.network.list() == {
                u'net-01': {u'network_id': u'1001', u'projects': [u'proj-01']},
                u'net-02': {u'network_id': u'1002', u'projects': [u'proj-01']},
                u'net-03': {u'network_id': u'1003', u'projects': [u'proj-01']},
                u'net-04': {u'network_id': u'1004', u'projects': [u'proj-02']},
                u'net-05': {u'network_id': u'1005', u'projects': [u'proj-02']}
                }

    def test_list_network_attachments(self):
        """ Test list of network attachments """
        assert C.network.list_network_attachments("net-01", "all") == {}
        assert C.network.list_network_attachments("net-02", "proj-01") == {}
        C.node.connect_network('node-01', 'eth0', 'net-03', 'vlan/native')
        deferred.apply_networking()
        assert C.network.list_network_attachments("net-03", "all") == {
                'node-01': {'project': 'proj-01',
                            'nic': 'eth0',
                            'channel': 'vlan/native'}
                }

    def test_network_show(self):
        """ Test show network. """
        assert C.network.show('net-01') == {
                u'access': [u'proj-01'],
                u'channels': [u'vlan/native', u'vlan/1001'],
                u'name': u'net-01',
                u'owner': u'proj-01',
                u'connected-nodes': {},
                }

    def test_network_show_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.network.show('net/%]-01')

    def test_network_create(self):
        """ Test create network. """
        assert C.network.create('net-abcd', 'proj-01', 'proj-01', '') is None

    def test_network_create_duplicate(self):
        """ Test error condition in create network. """
        C.network.create('net-123', 'proj-01', 'proj-01', '')
        with pytest.raises(FailedAPICallException):
            C.network.create('net-123', 'proj-01', 'proj-01', '')

    def test_network_create_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.network.create('net/%]-123', 'proj-01', 'proj-01', '')

    def test_network_delete(self):
        """ Test network deletion """
        C.network.create('net-xyz', 'proj-01', 'proj-01', '')
        assert C.network.delete('net-xyz') is None

    def test_network_delete_duplicate(self):
        """ Test error condition in delete network. """
        C.network.create('net-xyz', 'proj-01', 'proj-01', '')
        C.network.delete('net-xyz')
        with pytest.raises(FailedAPICallException):
            C.network.delete('net-xyz')

    def test_network_delete_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.network.delete('net/%]-xyz')

    def test_network_grant_project_access(self):
        """ Test granting  a project access to a network. """
        C.network.create('newnet01', 'admin', '', '')
        assert C.network.grant_access('proj-02', 'newnet01') is None
        assert C.network.grant_access('proj-03', 'newnet01') is None

    def test_network_grant_project_access_error(self):
        """ Test error while granting a project access to a network. """
        C.network.create('newnet04', 'admin', '', '')
        C.network.grant_access('proj-02', 'newnet04')
        with pytest.raises(FailedAPICallException):
            C.network.grant_access('proj-02', 'newnet04')

    def test_network_grant_project_access_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.network.grant_access('proj/%]-02', 'newnet04')

    def test_network_revoke_project_access(self):
        """ Test revoking a project's access to a network. """
        C.network.create('newnet02', 'admin', '', '')
        C.network.grant_access('proj-02', 'newnet02')
        assert C.network.revoke_access('proj-02', 'newnet02') is None

    def test_network_revoke_project_access_error(self):
        """
        Test error condition when revoking project's access to a network.
        """
        C.network.create('newnet03', 'admin', '', '')
        C.network.grant_access('proj-02', 'newnet03')
        C.network.revoke_access('proj-02', 'newnet03')
        with pytest.raises(FailedAPICallException):
            C.network.revoke_access('proj-02', 'newnet03')

    def test_network_revoke_project_access_reserved_chars(self):
        """ test for catching illegal argument characters"""
        with pytest.raises(BadArgumentError):
            C.network.revoke_access('proj/%]-02', 'newnet03')


class Test_extensions:
    """ Test extension related client calls. """

    def test_extension_list(self):
        """ Test listing active extensions. """
        assert C.extensions.list_active() == [
                    "hil.ext.auth.database",
                    "hil.ext.network_allocators.vlan_pool",
                    "hil.ext.obm.mock",
                    "hil.ext.switches.mock",
                ]


class TestShowNetworkingAction:
    """Test calls to show networking action method"""

    def test_show_networking_action(self):
        """(successful) call to show_networking_action"""
        response = C.node.connect_network(
                'node-01', 'eth0', 'net-01', 'vlan/native'
                )
        status_id = response['status_id']

        response = C.node.show_networking_action(status_id)
        assert response == {'status': 'PENDING',
                            'node': 'node-01',
                            'nic': 'eth0',
                            'type': 'modify_port',
                            'channel': 'vlan/native',
                            'new_network': 'net-01'}

        deferred.apply_networking()
        response = C.node.show_networking_action(status_id)
        assert response['status'] == 'DONE'

    def test_show_networking_action_fail(self):
        """(unsuccessful) call to show_networking_action"""
        with pytest.raises(FailedAPICallException):
            C.node.show_networking_action('non-existent-entry')
