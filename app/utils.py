import bisect
import collections
import re

import netaddr
from shelljob import proc

DB_FILE = "/tmp/db.ini"


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
    params_fixed = ["crudini", "--set", DB_FILE, cidr_dict.get("id")]
    for k in ["family", "cidr"]:
        proc.call(params_fixed + [k, cidr_dict.get(k)], shell=False, check_exit_code=True)


def read_cidr(cidr_id):
    return read_cidrs(family_filter=None, cidr_id_filter=cidr_id)


def delete_cidr(cidr_id):
    params = ["crudini", "--del", DB_FILE, str(cidr_id)]
    _raw_output, exit_code = proc.call(params, shell=False, check_exit_code=False)
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
        cidr_dict = {"id": str(cidr_id), "family": cidr_attrs.get("family"),
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
