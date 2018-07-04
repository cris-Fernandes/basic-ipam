import bisect
import collections
import re

import netaddr
from shelljob import proc

DB_FILE = "/tmp/db.ini"


def get_next_id():
    params = ["--get", DB_FILE, "globals", "next_id"]
    cmd = ["crudini"]
    rawOutput, exit_code = proc.call(cmd + params, shell=False, check_exit_code=False)
    if exit_code:
        return 1
    return int(rawOutput)


def set_next_id(next_cidr_id):
    params = ["--set", DB_FILE, "globals", "next_id", str(next_cidr_id)]
    cmd = ["crudini"]
    rawOutput, exit_code = proc.call(cmd + params, shell=False, check_exit_code=False)
    return exit_code


def save_cidr(cidrDict):
    paramsFixed = ["--set", DB_FILE, cidrDict.get("id")]
    cmd = ["crudini"]
    for k in ["family", "cidr"]:
        proc.call(cmd + paramsFixed + [k, cidrDict.get(k)], shell=False, check_exit_code=True)


def read_cidr(cidr_id):
    paramsFixed = ["--get", DB_FILE, str(cidr_id)]
    cmd = ["crudini"]
    cidrDict = {"id": str(cidr_id)}
    for k in ["family", "cidr"]:
        rawOutput, exit_code = proc.call(cmd + paramsFixed + [k],
                                         shell=False, check_exit_code=False)
        if exit_code:
            return None
        cidrDict[k] = str(rawOutput).strip()
    return cidrDict


# Ref: https://stackoverflow.com/questions/18969801/best-approach-to-detect-subnet-overlap-in-a-postgresql-db#18970054  # noqa
def _subnets_overlap(subnets):
    # ranges will be a sorted list of alternating start and end addresses
    ranges = []
    for subnet in subnets:
        # find indices to insert start and end addresses
        first = bisect.bisect_left(ranges, subnet.first)
        last = bisect.bisect_right(ranges, subnet.last)
        # check the overlap conditions and return if one is met
        if first != last or first % 2 == 1:
            return True
        ranges[first:first] = [subnet.first, subnet.last]
    return False


def check_overlap(network):
    # TODO (FF): maybe upconvert, so we check overlap on ipv4 to ipv6
    # e.g. IPNetwork('::ffff:192.0.2.1/119').ipv6(ipv4_compatible=True)
    cidrs = read_cidrs(familyFilter=str(network.version))
    for cidrDict in cidrs:
        currNetwork = netaddr.IPNetwork(cidrDict.get("cidr"))
        if _subnets_overlap([currNetwork, network]):
            return True
    return False


def read_cidrs(familyFilter=None):
    cidrRaw = ''
    cmd = ['crudini', '--get', '--format=lines', DB_FILE]
    output, exit_code = proc.call(cmd, shell=False, check_exit_code=False)
    if output and exit_code == 0:
        cidrRaw = str(output)
    cidrsDict = parseCidrRaw(cidrRaw)
    cidrs = []
    od = collections.OrderedDict(sorted(cidrsDict.items()))
    for cidr_id, cidr_attrs in od.items():
        if familyFilter and cidr_attrs.get("family") != familyFilter:
            continue
        cidrDict = {"id": str(cidr_id), "family": cidr_attrs.get("family"),
                    "cidr": cidr_attrs.get("cidr")}
        cidrs.append(cidrDict)
    return cidrs


def parseCidrRaw(cidrRaw):
    cidrs = {}
    try:
        cidrRawLines = cidrRaw.split('\n')
    except Exception:
        cidrRawLines = []
    for cidr in cidrRawLines:
        # Parse line from crudini output. It should look like this:
        # [id] key = value  ==> [2] family = 6
        match = re.search(r"^\s*\[\s*(\d+)\s*\]\s*(\S+)\s*=\s*(.+)$", cidr)
        if match:
            cidr_id = match.group(1)
            cidrDict = cidrs.get(cidr_id, {})
            cidrDict[match.group(2)] = match.group(3)
            cidrs[cidr_id] = cidrDict
    return cidrs
