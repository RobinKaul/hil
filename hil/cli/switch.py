"""Commands related to switch are in this module"""
import click
import sys
import ast
from hil.cli.client_setup import client
from prettytable import PrettyTable

@click.group()
def switch():
    """Commands related to switch"""


@switch.command(name='show')
@click.argument('switch')
def switch_show(switch):
    """Display information about <switch>"""
    q = client.switch.show(switch)
    x = PrettyTable()
    x.field_names = ['Attribute', 'Information']    
    for item, value in q.iteritems():
	if isinstance(value, list):
	    value = value[0]
	if isinstance(item, unicode):
            item  = item.encode("utf-8")
	
	if item == 'ports':		
            #print(item.encode("utf-8"), value.encode("utf-8"))
            #x.add_row(item.encode("utf-8"), value.encode("utf-8"))
	    for portDictItem, portDictValue in value.iteritems():
		x.add_row([item, ":".join([portDictItem.encode("utf-8"), portDictValue.encode("utf-8")])])
	else:
	    x.add_row([item, value.encode("utf-8")])

    print(x)

@switch.command(name='list')
def list_switches():
    """List all switches"""
    q = client.switch.list()
    x=PrettyTable(['switch list'])
    for switch in q:
        x.add_row([switch])
    print(x)
    

@switch.command(name='register', short_help='Register a switch')
@click.argument('switch')
@click.argument('subtype')
@click.argument('args', nargs=-1)
def switch_register(switch, subtype, args):
    """Register a switch with name <switch> and
    <subtype>, <hostname>, <username>,  <password>

    eg. hil switch_register mock03 mock mockhost01 mockuser01 mockpass01

    To make a generic switch register call, pass the arguments like:

    hil switch_register switchname subtype switchinfo
    hil switch_register dell-1 'http://example.com/schema/url' '{"foo": "bar"}'
    """
    switch_api = "http://schema.massopencloud.org/haas/v0/switches/"

    if subtype == "nexus" or subtype == "delln3000":
        if len(args) == 4:
            switchinfo = {
                "hostname": args[0],
                "username": args[1],
                "password": args[2],
                "dummy_vlan": args[3]}
            subtype = switch_api + subtype
        else:
            sys.exit('ERROR: subtype ' + subtype +
                     ' requires exactly 4 arguments\n'
                     '<hostname> <username> <password>'
                     '<dummy_vlan_no>\n')

    elif subtype == "mock" or subtype == "powerconnect55xx":
        if len(args) == 3:
            switchinfo = {"hostname": args[0],
                          "username": args[1], "password": args[2]}
            subtype = switch_api + subtype
        else:
            sys.exit('ERROR: subtype ' + subtype +
                     ' requires exactly 3 arguments\n'
                     '<hostname> <username> <password>\n')

    elif subtype == "brocade" or subtype == "dellnos9":
        if len(args) == 4:
            switchinfo = {"hostname": args[0],
                          "username": args[1], "password": args[2],
                          "interface_type": args[3]}
            subtype = switch_api + subtype
        else:
            sys.exit('ERROR: subtype ' + subtype +
                     ' requires exactly 4 arguments\n'
                     '<hostname> <username> <password> '
                     '<interface_type>\n'
                     'NOTE: interface_type refers '
                     'to the speed of the switchports\n '
                     'ex. TenGigabitEthernet, FortyGigabitEthernet, '
                     'etc.\n')
    elif subtype == "ovs":
        if len(args) == 1:
            switchinfo = {"ovs_bridge": args[0]}
            subtype = switch_api + subtype
        else:
            sys.exit('ERROR: subtype ' + subtype +
                     ' requires exactly 1 arguments\n'
                     '<ovs_bridge> \n')

    else:
        if len(args) == 0:
            sys.exit('No switchinfo provided')
        try:
            switchinfo = ast.literal_eval(args[0])
        except (ValueError, SyntaxError):
            sys.exit('Malformed switchinfo')

    client.switch.register(switch, subtype, switchinfo)


@switch.command(name='delete')
@click.argument('switch')
def switch_delete(switch):
    """Delete a <switch> """
    client.switch.delete(switch)
