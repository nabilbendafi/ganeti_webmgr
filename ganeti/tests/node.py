# Copyright (C) 2010 Oregon State University et al.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

from datetime import datetime

from django.db.utils import IntegrityError
from django.test import TestCase
from django.test.client import Client


from util import client
from ganeti.tests.rapi_proxy import RapiProxy, NODE
from ganeti import models
Cluster = models.Cluster
Node = models.Node


__all__ = (
    'TestNodeModel',
    'TestNodeViews',
)


class NodeTestCaseMixin():
    def create_node(self, cluster=None, hostname='node1.osuosl.bak'):
        cluster = cluster if cluster else Cluster.objects \
            .create(hostname='test.osuosl.bak', slug='OSL_TEST')
        node = Node.objects.create(cluster=cluster, hostname=hostname)
        return node, cluster


class TestNodeModel(TestCase, NodeTestCaseMixin):
    
    def setUp(self):
        self.tearDown()
        models.client.GanetiRapiClient = RapiProxy

    def tearDown(self):
        Node.objects.all().delete()
        Cluster.objects.all().delete()
    
    def test_trivial(self):
        """
        Test instantiating a VirtualMachine
        """
        Node()
    
    def test_non_trivial(self):
        """
        Test instantiating a VirtualMachine with extra parameters
        """
        # Define cluster for use
        node_hostname='node.test.org'
        cluster = Cluster.objects.create(hostname='test.osuosl.bak', slug='OSL_TEST')
        
        # Cluster
        node = Node.objects.create(cluster=cluster, hostname=node_hostname)
        self.assertTrue(node.id)
        self.assertEqual('node.test.org', node.hostname)
        self.assertFalse(node.error)
        node.delete()
        
        # Multiple
        node = Node.objects.create(cluster=cluster, hostname=node_hostname,
                    ram=512, disk=5120)
        self.assertTrue(node.id)
        self.assertEqual('node.test.org', node.hostname)
        self.assertEqual(512, node.ram)
        self.assertEqual(5120, node.disk)
        self.assertFalse(node.error)
        
        # test unique constraints
        node = Node(cluster=cluster, hostname=node_hostname)
        self.assertRaises(IntegrityError, node.save)
        
        # Remove cluster
        Cluster.objects.all().delete();
    
    def test_save(self):
        """
        Test saving a VirtualMachine
        
        Verify:
            * Node can be saved
            * Node can be loaded
            * Hash is copied from cluster
        """
        node, cluster = self.create_node()
        self.assert_(node.id)
        self.assertFalse(node.error)
        self.assertEqual(node.cluster_hash, cluster.hash)
        
        node = Node.objects.get(id=node.id)
        self.assert_(node.info)
        self.assertFalse(node.error)
    
    def test_hash_update(self):
        """
        When cluster is saved hash for its VirtualMachines should be updated
        """
        node0, cluster = self.create_node()
        node1, cluster = self.create_node(cluster, 'test2.osuosl.bak')
        
        self.assertEqual(node0.cluster_hash, cluster.hash)
        self.assertEqual(node1.cluster_hash, cluster.hash)
        
        # change cluster's hash
        cluster.hostname = 'SomethingDifferent'        
        cluster.save()
        node0 = Node.objects.get(pk=node0.id)
        node1 = Node.objects.get(pk=node1.id)
        self.assertEqual(node0.cluster_hash, cluster.hash, 'VirtualMachine does not have updated cache')
        self.assertEqual(node1.cluster_hash, cluster.hash, 'VirtualMachine does not have updated cache')
    
    def test_parse_info(self):
        """
        Test parsing values from cached info
        
        Verifies:
            * mtime and ctime are parsed
            * ram, virtual_cpus, and disksize are parsed
        """
        node, cluster = self.create_node()
        node.info = NODE
        
        self.assertEqual(node.ctime, datetime.fromtimestamp(1285799513.4741000))
        self.assertEqual(node.mtime, datetime.fromtimestamp(1285883187.8692000))
        self.assertEqual(node.ram, 1111)
        self.assertEqual(node.disk, 2222)
        self.assertEqual(node.ram_total, 9999)
        self.assertEqual(node.disk_total, 6666)
        self.assertFalse(node.offline)


class TestNodeViews(TestCase, NodeTestCaseMixin):
    pass
    