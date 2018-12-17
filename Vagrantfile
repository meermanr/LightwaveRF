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
    # d.run "influxdb:1.7.2-alpine",
    #  args: "-p 8086:8086 -v influxdb_data:/var/lib/influxdb",
    #  cmd: "influxdb"
    d.run "prom/prometheus",
      args: "-p 9090:9090 -v prometheus-data:/prometheus"
  end
end
