# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  config.vm.box = "bento/ubuntu-18.04"
  config.vm.network "public_network"

  config.vm.provider "virtualbox" do |vb|
    vb.memory = "1024"
  end

  config.vm.provision "docker" do |docker|
    docker.images = ["influxdb:1.7.2-alpine"]
    # docker.run "influxdb:1.7.2-alpine",
    #  args: "-p 8086:8086 -v influxdb_data:/var/lib/influxdb",
    #  cmd: "influxdb"

    # Note: Listens on TCP 9090 (HTTP), but want it to connect to Python's
    # prometheus_client that runs outside Docker
    docker.run "prom/prometheus",
      args: "--net=host -v prometheus-data:/prometheus -v /vagrant/prometheus.yml:/etc/prometheus/prometheus.yml"
  end
end
