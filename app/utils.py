import bisect
import collections
import re
import time
from datetime import datetime

import netaddr
from shelljob import proc

DB_FILE = "/tmp/db.ini"
DEFAULT_CIDR_ID = 1
CIDR_ALLOC_SECTION = "allocations_pool_{}"


def get_next_id():
    params = ["crudini", "--get", DB_FILE, "globals", "next_id"]
    raw_output, exit_code = proc.call(params, shell=False, check_exit_code=False)
    if exit_code:
        return 1
    return int(raw_output)


def set_next_id(next_cidr_id):
    params = ["crudini", "--set", DB_FILE, "globals", "next_id", str(next_cidr_id)]
    _raw_output, exit_code = proc.call(params, shell=False, check_exit_code=False)
    return exit_code


def save_cidr(cidr_dict):
    params_fixed = ["crudini", "--set", DB_FILE, cidr_dict.get("subnet_id")]
    for k in ["family", "cidr"]:
        proc.call(params_fixed + [k, cidr_dict.get(k)], shell=False, check_exit_code=True)


def read_cidr(cidr_id):
    return read_cidrs(family_filter=None, cidr_id_filter=cidr_id)


def delete_cidr(cidr_id):
    params = ["crudini", "--del", DB_FILE, str(cidr_id)]
    _raw_output, exit_code = proc.call(params, shell=False, check_exit_code=False)
    if not exit_code:
        # Purge away all known allocations to this cidr.
        # Maybe that should prevent cidr from being removed?
        _raw_output, exit_code = _delete_cidr_allocation(cidr_id)
    return exit_code


# Ref: https://stackoverflow.com/questions/18969801/best-approach-to-detect-subnet-overlap-in-a-postgresql-db#18970054  # noqa
def _subnets_overlap(subnets):
    # ranges will be a sorted list of alternating start and end addresses
    ranges = []
    for subnet in subnets:
        # find indices to insert start and end addresses
        # Ref: https://docs.python.org/2/library/bisect.html

        # look for index in existing range values that have greater than or equal value than
        # current subnet start value
        offset1 = bisect.bisect_left(ranges, subnet.first)

        # look for index in existing range values that have less or equal value than
        # current subnet stop value
        offset2 = bisect.bisect_right(ranges, subnet.last)

        # check the overlap conditions and return if one is met:
        # * offset1 and offset2 must be the same
        # * range grows by 2. So index they fall into must be either 0 or even
        if offset1 != offset2 or offset1 % 2 == 1:
            return True

        # insert subnet's first and last values in ranges for next iteration check
        ranges[offset1:offset1] = [subnet.first, subnet.last]
    return False


def check_overlap(network):
    # TODO (FF): maybe upconvert, so we check overlap on ipv4 to ipv6
    # e.g. IPNetwork('::ffff:192.0.2.1/119').ipv6(ipv4_compatible=True)
    cidrs = read_cidrs(family_filter=str(network.version))
    for cidrDict in cidrs:
        curr_network = netaddr.IPNetwork(cidrDict.get("cidr"))
        if _subnets_overlap([curr_network, network]):
            return True
    return False


def read_cidrs(family_filter=None, cidr_id_filter=None):
    cidr_raw = ''
    params = ['crudini', '--get', '--format=lines', DB_FILE]
    if cidr_id_filter:
        params.append(str(cidr_id_filter))
    output, exit_code = proc.call(params, shell=False, check_exit_code=False)
    if output and exit_code == 0:
        cidr_raw = str(output)
    cidrs_dict = _parse_cidr_raw(cidr_raw)
    cidrs = []
    od = collections.OrderedDict(sorted(cidrs_dict.items()))
    for cidr_id, cidr_attrs in od.items():
        if family_filter and cidr_attrs.get("family") != family_filter:
            continue
        cidr_dict = {"subnet_id": str(cidr_id), "family": cidr_attrs.get("family"),
                     "cidr": cidr_attrs.get("cidr")}
        cidrs.append(cidr_dict)
    return cidrs


def _parse_cidr_raw(cidr_raw):
    cidrs = {}
    try:
        cidr_raw_lines = cidr_raw.split('\n')
    except Exception:
        cidr_raw_lines = []
    for cidr in cidr_raw_lines:
        # Parse line from crudini output. It should look like this:
        # [id] key = value  ==> [2] family = 6
        match = re.search(r"^\s*\[\s*(\d+)\s*\]\s*(\S+)\s*=\s*(.+)$", cidr)
        if match:
            cidr_id = match.group(1)
            cidr_dict = cidrs.get(cidr_id, {})
            cidr_dict[match.group(2)] = match.group(3)
            cidrs[cidr_id] = cidr_dict
    return cidrs


def allocate_addr(cidr_id):
    if not cidr_id:
        cidr_id = DEFAULT_CIDR_ID
    cidr_dict, allocations = _read_cidr_allocations(cidr_id)
    if cidr_dict is None:
        return None, "invalid address pool"
    network = netaddr.IPNetwork(cidr_dict.get("cidr"))
    ip_range = netaddr.iter_iprange(network.first, network.last)
    for address_iter in ip_range:
        address = str(address_iter)
        if address in allocations:
            continue
        address_dict = {"subnet_id": cidr_dict.get("subnet_id"), "address": address}
        raw_output, exit_code = _write_cidr_allocation(cidr_id, address)
        if exit_code:
            return None, "write error {} {}".format(exit_code, raw_output)
        return address_dict, ''
    return None, 'pool is depleted'


def deallocate_addr(cidr_id, address):
    if not cidr_id:
        cidr_id = DEFAULT_CIDR_ID
    if not address:
        return "no valid address provided for deallocation"
    # idem-potent
    raw_output, exit_code = _delete_cidr_allocation(cidr_id, address)
    if exit_code:
        return "write error {} {}".format(exit_code, raw_output)
    return None


def read_subnet_allocations(cidr_id):
    _cidr_dict, allocations = _read_cidr_allocations(cidr_id)
    return list(allocations)


def _parse_allocations_raw(allocations_raw):
    allocations = []
    try:
        allocations_raw_lines = allocations_raw.split('\n')
    except Exception:
        allocations_raw_lines = []
    for allocation_raw_line in allocations_raw_lines:
        # Parse line from crudini output. It should look like this:
        # [id] key = value  ==> [ allocations_pool_1 ] 2001_db8__ = 2018-01-01_01:01:01
        match = re.search(r"^\s*\[\s*(.+)\s*\]\s*(\S+)\s*=\s*(.+)$", allocation_raw_line)
        if match:
            address_encoded = match.group(2)
            # decode address in a way where '_' is replaced with ':'.
            # This was done to make crudini happy
            address = address_encoded.replace('_', ':')
            allocations.append(str(address))
    return allocations


def _read_cidr_allocations(cidr_id):
    section = CIDR_ALLOC_SECTION.format(cidr_id)
    allocations = set()
    # Make sure cidr_id exists
    cidr_dicts = read_cidrs(family_filter=None, cidr_id_filter=cidr_id)
    if not cidr_dicts:
        return None, allocations
    cidr_dict = cidr_dicts[0]
    params = ['crudini', '--get', '--format=lines', DB_FILE, section]
    output, exit_code = proc.call(params, shell=False, check_exit_code=False)
    if exit_code == 0:
        allocations.update(_parse_allocations_raw(output))
    return cidr_dict, allocations


def _write_cidr_allocation(cidr_id, address):
    ts = time.time()
    st = datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S %Z')
    return _update_cidr_allocation(cidr_id, "--set", address, st)


def _delete_cidr_allocation(cidr_id, address=None):
    return _update_cidr_allocation(cidr_id, "--del", address)


def _update_cidr_allocation(cidr_id, operation, address, value=None):
    section = CIDR_ALLOC_SECTION.format(cidr_id)
    params = ['crudini', operation, DB_FILE, section]
    if address:
        # encode address in a way where ':' is replaced with '_'. This is to make crudini happy
        address_encoded = address.replace(':', '_')
        params.append(address_encoded)
    if value:
        params.append(value)
    output, exit_code = proc.call(params, shell=False, check_exit_code=False)
    return output, exit_code
