"""Commands related to networks are in this module"""
import click
import sys
from hil.cli.client_setup import client
from prettytable import PrettyTable
import json


@click.group()
def network():
    """Commands related to network"""


@network.command(name='create', short_help='Create a new network')
@click.argument('network')
@click.argument('owner')
@click.option('--access', help='Projects that can access this network. '
              'Defaults to the owner of the network')
@click.option('--net-id',
              help='Network ID for network. Only admins can specify this.')
def network_create(network, owner, access, net_id):
    """Create a link-layer <network>.  See docs/networks.md for details"""
    if net_id is None:
        net_id = ''
    if access is None:
        access = owner
    client.network.create(network, owner, access, net_id)


@network.command(name='delete')
@click.argument('network')
def network_delete(network):
    """Delete a network"""
    client.network.delete(network)


@network.command(name='show')
@click.argument('network')
@click.option('--jsonout', is_flag=True)
def network_show(network, jsonout):
    """Display information about network"""
    raw_output = client.network.show(network)

    if jsonout:
        json_output = json.dumps(raw_output)
        print(json_output)
        return

    net_table = PrettyTable()
    net_table.field_names = ['ATTRIBUTE', 'INFORMATION']

    if 'owner' in raw_output:
        net_table.add_row(['Owner', raw_output['owner']])
    if 'name' in raw_output:
        net_table.add_row(['Name', raw_output['name']])
    if 'access' in raw_output:
        net_table.add_row(['Access', raw_output['access'][0]])
        for i in range(1, len(raw_output['access'])):
            net_table.add_row(['', raw_output['access'][i]])
    if 'channels' in raw_output:
        net_table.add_row(['Channels', raw_output['channels'][0]])
        for i in range(1, len(raw_output['channels'])):
            net_table.add_row(['', raw_output['channels'][i]])
    if 'connected-nodes' in raw_output:
        firstElement = 0
        for node, nic in raw_output['connected-nodes'].items():
            if firstElement == 0:
                net_table.add_row(['Connected Nodes', node + "->" + nic[0]])
                firstElement+= 1
            else:
                net_table.add_row(['', node + "->" + nic[0]])

            for i in range(1, len(nic)):
                net_table.add_row(['', node + "->" + nic[i]])

    print(net_table)


@network.command(name='list')
@click.option('--jsonout', is_flag=True)
def network_list(jsonout):
    """List all networks"""
    raw_output = client.network.list()

    if jsonout:
        json_output = json.dumps(raw_output)
        print(json_output)
        return

    net_table = PrettyTable()
    net_table.field_names = ['NETWORK NAME', 'NETWORK ID', 'PROJECTS WITH ACCESS']
    for net_name, value in raw_output.items():
        if 'network_id' in value:
            net_id = value['network_id']
        if 'projects' in value:
            net_table.add_row([net_name, net_id, value['projects'][0]])
            for i in range(1, len(value['projects'])):
                net_table.add_row(['','', value['projects'][i]])
    print(net_table)


@network.command('list-attachments')
@click.argument('network')
@click.option('--project', help='Name of project.')
def list_network_attachments(network, project):
    """Lists all the attachments from <project> for <network>

    If <project> is `None`, lists all attachments for <network>
    """
    print(client.network.list_network_attachments(network, project))


@network.command(name='grant-access')
@click.argument('network')
@click.argument('project')
def network_grant_project_access(project, network):
    """Add <project> to <network> access"""
    client.network.grant_access(project, network)


@network.command(name='revoke-access')
@click.argument('network')
@click.argument('project')
def network_revoke_project_access(project, network):
    """Remove <project> from <network> access"""
    client.network.revoke_access(project, network)
