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
    cidr_dict = {"subnet_id": str(next_id), "family": str(network.version), "cidr": str(network)}

    utils.set_next_id(next_id + 1)
    utils.save_cidr(cidr_dict)
    return make_response(jsonify(cidr_dict))


@app.route('/subnets', methods=['GET'])
def get_subnet():
    family_filter = request.args.get('family')
    cidrs = utils.read_cidrs(family_filter)
    return jsonify(cidrs)


@app.route('/subnet/<subnet_id>', methods=['GET'])
def get_subnet_entry(subnet_id):
    cidrs = utils.read_cidr(subnet_id)
    return jsonify(cidrs)


@app.route('/subnet/<subnet_id>', methods=['DELETE'])
def delete_subnet_entry(subnet_id):
    rc = utils.delete_cidr(subnet_id)
    if rc:
        return make_response(
            jsonify({'error': 'failed delete {} with rc {}'.format(subnet_id, rc)}), 400)
    return '', 204


@app.route('/subnet_address', methods=['POST'])
def allocate_addr_default_cidr():
    subnet_id = None
    if request.json:
        subnet_id = request.json.get('subnet_id')
    return _allocate_addr(subnet_id=subnet_id)


@app.route('/subnet_address/<subnet_id>', methods=['POST'])
def allocate_addr(subnet_id):
    return _allocate_addr(subnet_id=subnet_id)


@app.route('/subnet_address', methods=['DELETE'])
def deallocate_addr_default_cidr1():
    subnet_id = None
    if request.json:
        subnet_id = request.json.get('subnet_id')
        address = request.json.get('address')
    return _deallocate_addr(subnet_id=subnet_id, address=address)


@app.route('/subnet_address/<address>', methods=['DELETE'])
def deallocate_addr_default_cidr2(address):
    subnet_id = None
    if request.json:
        subnet_id = request.json.get('subnet_id')
    return _deallocate_addr(subnet_id=subnet_id, address=address)


@app.route('/subnet_address/<subnet_id>/<address>', methods=['DELETE'])
def deallocate_addr(subnet_id, address):
    return _deallocate_addr(subnet_id=subnet_id, address=address)


@app.route('/subnet_address/<subnet_id>', methods=['GET'])
def get_subnet_allocations(subnet_id):
    allocations = utils.read_subnet_allocations(subnet_id)
    return jsonify(allocations)


def _allocate_addr(subnet_id):
    addr, msg = utils.allocate_addr(cidr_id=subnet_id)
    if not addr:
        if not subnet_id:
            subnet_id = "default"
        return make_response(
            jsonify({'error': 'failed allocate from subnet_id {}: {}'.format(
                subnet_id, msg)}), 400)
    return jsonify(addr)


def _deallocate_addr(subnet_id, address):
    msg = utils.deallocate_addr(cidr_id=subnet_id, address=address)
    if msg:
        if not subnet_id:
            subnet_id = "default"
        return make_response(
            jsonify({'error': 'failed deallocate {} from subnet_id {}: {}'.format(
                address, subnet_id, msg)}), 400)
    return '', 204
