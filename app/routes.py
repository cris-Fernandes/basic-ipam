import os
import netaddr
from flask import abort
from flask import jsonify
from flask import make_response
from flask import request

from app import app
from app import utils


@app.route('/')
def index():
    return os.environ.get("MSG", "Hello, World!")


@app.route('/subnets', methods=['POST'])
def create_subnet():
    if not request.json:
        abort(400)

    cidrParam = request.json.get('cidr')
    try:
        network = netaddr.IPNetwork(cidrParam)
    except Exception:
        return make_response(
            jsonify({'error': 'bad format attribute: {} {}'.format('cidr', cidrParam)}), 400)

    # avoid duplicates and overlaps
    if utils.check_overlap(network):
        return make_response('subnet overlaps with existing subnet\n', 400)

    next_id = utils.get_next_id()
    cidrDict = {"id": str(next_id), "family": str(network.version), "cidr": str(network)}

    utils.save_cidr(cidrDict)
    utils.set_next_id(next_id + 1)
    return make_response(jsonify(cidrDict))


@app.route('/subnets', methods=['GET'])
def get_subnet():
    familyFilter = request.args.get('family')
    cidrs = utils.read_cidrs(familyFilter)
    return jsonify(cidrs)
