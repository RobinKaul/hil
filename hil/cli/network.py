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
@click.option('--json', is_flag=True)
def network_show(network, json):
    """Display information about network"""
    q = client.network.show(network)
    if json:
        print q
        return
    net_table = PrettyTable()
    net_table.field_names = ['Attribute', 'Info']

    if 'owner' in q:
	net_table.add_row(['owner', q['owner']])
	net_table.add_row(['',''])
    if 'name' in q:
	net_table.add_row(['name', q['name']])
	net_table.add_row(['',''])
    if 'access' in q:
	net_table.add_row(['access', q['access'][0]])
	net_table.add_row(['',''])
    if 'channels' in q:
	net_table.add_row(['channels', q['channels'][0]])
	for i in range(1, len(q['channels'])):
	    net_table.add_row(['', q['channels'][i]])
	net_table.add_row(['',''])
    if 'connected-nodes' in q:
	firstElement = 0
	for subVal in q['connected-nodes'].iteritems():
	    temp = []
	    temp.append(subVal[0])
	    temp.append(subVal[1][0])
	    if firstElement == 0:
		net_table.add_row(['connected-nodes', "->".join(temp)])
		firstElement+= 1
	    else:
		net_table.add_row(['', "->".join(temp)])
    print net_table

'''
@network.command(name='show')
@click.argument('network')
@click.option('--json', is_flag=True)
def network_show(network, json):
    """Display information about network"""
    q = client.network.show(network)
    if json:
        print q
        return
    import pdb; pdb.set_trace()
    net_table = PrettyTable()
    net_table.field_names = ['Attribute', 'Info']
    for item, value in q.iteritems():
        if isinstance(value, list):
            net_table.add_row([item, value[0]])
	    for i in range(1, len(value)):
                net_table.add_row(['', value[i]])

	elif isinstance(value, dict):
	    for subVal in value.iteritems():
		temp = []
		temp.append(subVal[0])
		temp.append(subVal[1][0])
		net_table.add_row([item, "->".join(temp)])
	else:
	    net_table.add_row([item, value])
    print net_table
'''

@network.command(name='list')
@click.option('--json', is_flag=True)
def network_list(json):
    """List all networks"""
    q = client.network.list()
    if json:
        print q
        return
    count=0
    net_table = PrettyTable()
    net_table.field_names = ['network name','network id','project name']
    for key1,value1 in q.iteritems():
        for key2,value2 in value1.iteritems():
            if count%2==0:
                pid=value2
            else:
                pname=value2
            count+=1
        net_table.add_row([key1,pid,pname[0].encode("utf-8")])
    print net_table
    



@network.command('list-attachments')
@click.argument('network')
@click.option('--project', help='Name of project.')
def list_network_attachments(network, project):
    """Lists all the attachments from <project> for <network>

    If <project> is `None`, lists all attachments for <network>
    """
    print client.network.list_network_attachments(network, project)


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
