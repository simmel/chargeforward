#!/usr/bin/env python
# vim: set fileencoding=utf8
import os, subprocess, time, signal, sys, json, urllib, urllib2, argparse, socket

parser = argparse.ArgumentParser(description='Create a VM temporary on Digital Ocean to use as a SOCKS proxy.')
parser.add_argument('-f', '--fqdn', help='FQDN of your new VM, default: FQDN of your machine', default=socket.getfqdn())
parser.add_argument('-c', '--client-id', help='Your client ID at Digital Ocean', required=True)
parser.add_argument('-a', '--api-key', help='Your API-key at Digital Ocean', required=True)
parser.add_argument('-p', '--port', help='Port to use for SOCKS proxy', default=8080, type=int)
parser.add_argument('-l', '--local', help='Only bind to localhost', action="store_true", default=False)
parser.add_argument('-r', '--region', help='The slug-name of the region to launch you VPS in, e.g. nyc1')

args = parser.parse_args()
region = None
image = None

url = "https://api.digitalocean.com"
request = {
  "client_id": args.client_id,
  "api_key": args.api_key
}

images = json.load(urllib2.urlopen("%s/images/?%s" % (url, urllib.urlencode(dict(request.items() + {"filter": "my_images"}.items())))))["images"]

if len(images) == 0:
  print >> sys.stderr, ("No images available. Create your image first")
  sys.exit(1)

if len(images) == 1:
  print "Only found one image, picking that."
  image = images[0]['id']
  regions = images[0]['regions']
  if len(regions) == 1:
    region = regions[0]
  else:
    for k,v in enumerate(regions):
      print "%i. %s" % (v, images[0]['region_slugs'][k])

      while True:
          i = int(raw_input('In which region do you want to deploy?: '))
          if 0 <= i <= len(regions)-1:
              region = regions[i]
              break

if not image:
  for k,v in enumerate(images):
    print "%i. %s" % (k, v)

  while True:
    i = int(raw_input('Which image do you want to deploy?: '))
    if 0 <= i <= len(images)-1:
      image = images[i]["id"]
      image_dict = images[i]
      break

  for k,v in enumerate(image_dict['regions']):
    print "%i. %s" % (k, image_dict['region_slugs'][k])

    while True:
        i = int(raw_input('In which region do you want to deploy?: '))
        for k,v in enumerate(image_dict['regions']):
          if i == k:
            region = image_dict['regions'][k]
            break
        # Oh Python... http://stackoverflow.com/a/654002
        else:
          continue
        break

ssh_keys = json.load(urllib2.urlopen("%s/ssh_keys/?%s" % (url, urllib.urlencode(request))))["ssh_keys"]
ssh_keys = ",".join([str(s["id"]) for s in ssh_keys])

print "Deploying VM, waiting for it to be created."
droplet = json.load(urllib2.urlopen("%s/droplets/new?%s" % (url, urllib.urlencode(dict(request.items() + {"name": args.fqdn, "size_id": 66, "image_id": image, "region_id": region, "ssh_key_ids": ssh_keys}.items())))))

if droplet["status"] != "OK":
  print >> sys.stderr, droplet["error_message"]
  sys.exit(1)

droplet = droplet["droplet"]

ip_address = None
while True:
  d = json.load(urllib2.urlopen("%s/droplets/%i?%s" % (url, droplet["id"], urllib.urlencode(request))))["droplet"]
  e = json.load(urllib2.urlopen("%s/events/%i?%s" % (url, droplet["event_id"], urllib.urlencode(request))))
  percentage = int(e["event"]["percentage"] or 0)
  sys.stdout.write('\b\b\b%i%%' % (percentage))
  sys.stdout.flush()
  if d["status"] == "active":
    print("\b\b\bDeployed!")
    ip_address = d["ip_address"]
    break
  time.sleep(1)

ssh = None
should_run = True

def signal_handler(signal, frame):
  global should_run
  should_run = False
  print "\nGot ^C, killing ssh and destroying VM"
  d = json.load(urllib2.urlopen("%s/droplets/%i/destroy?%s" % (url, droplet["id"], urllib.urlencode(request))))
  ssh.kill()
  ssh.wait()
  if d["status"] == "OK":
    print "Everything destroyed correctly."
  else:
    print >> sys.stderr, ("Droplet (with id: %i and name: %s) not destroyed correctly, please correct manually." % (droplet["id"], args.fqdn))
    print d
    sys.exit(1)

signal.signal(signal.SIGINT, signal_handler)

def fork_ssh():
  with open(os.devnull, 'w') as devnull:
    global ssh
    ssh = subprocess.Popen(["ssh", "-N", "-oUserKnownHostsFile=/dev/null", "-oStrictHostKeyChecking=no", "-D %s%i" % ("0.0.0.0:" if not args.local else "", args.port), "root@%s" % ip_address], stdout=devnull, stderr=devnull)

if ssh == None:
  fork_ssh()

print "SOCKS-proxy up at port %i" % args.port
print "Press ^C to disconnect and destroy the VM"

while should_run:
  if ssh.poll() != None:
    fork_ssh()
  time.sleep(1)
