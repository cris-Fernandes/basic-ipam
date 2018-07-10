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

    cidr_param = request.json.get('cidr')
    try:
        network = netaddr.IPNetwork(cidr_param)
    except Exception:
        return make_response(
            jsonify({'error': 'bad format attribute: {} {}'.format('cidr', cidr_param)}), 400)

    # avoid duplicates and overlaps
    if utils.check_overlap(network):
        return make_response('subnet overlaps with existing subnet\n', 400)

    next_id = utils.get_next_id()
    cidr_dict = {"id": str(next_id), "family": str(network.version), "cidr": str(network)}

    utils.save_cidr(cidr_dict)
    utils.set_next_id(next_id + 1)
    return make_response(jsonify(cidr_dict))


@app.route('/subnets', methods=['GET'])
def get_subnet():
    family_filter = request.args.get('family')
    cidrs = utils.read_cidrs(family_filter)
    return jsonify(cidrs)
