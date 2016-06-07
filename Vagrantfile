Vagrant.configure('2') do |config|
  config.vm.box = './mininet.box'
  config.ssh.username = 'vagrant'
  config.ssh.password = 'vagrant'
  config.vm.synced_folder '.', '/home/mininet/pox-playground'
end
