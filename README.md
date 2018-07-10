# basic-ipam

A very basic implementation of flask app used
for storing a cidr address and checking for overlaps

```
# install deps
for x in $(cat bindep.txt); do echo $x ; sudo apt install -y $x ; done
sudo -H pip install -r requirements.txt

# run unit tests
sudo -H pip install tox && tox

# run in debug mode
H=0.0.0.0; P=8888
export FLASK_APP=ipam.py && FLASK_DEBUG=1 flask run --host $H --port $P --without-threads
```

Example REST calls:

```
sudo apt install -y jq

for currCidr in "2001:db8::/32" "1.1.1.4/31"; do \
  json=$(jq -n -r \
         --arg cidr "$currCidr" \
         '{cidr: $cidr}'
         )
  curl -H "Cache-Control: no-cache" -H "Content-Type: application/json" \
    -i -X POST -d "$json" http://localhost:8888/subnets
done

curl -i http://localhost:8888/subnets

curl -i http://localhost:8888/subnets?family=6

curl -i http://localhost:8888/subnet/1

curl -i -X DELETE http://localhost:8888/subnet/1
```