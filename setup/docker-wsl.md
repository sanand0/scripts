# Install Docker on WSL 2

[Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/)

```sh
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

sudo service docker start

sudo groupadd docker
sudo usermod -aG docker ${USER}
```

Log out and log in. Then:

```shell
docker run hello-world
```

# Install Docker on WSL 2 with GPU

[Install NVIDIA Container Toolkit in WSL](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

```sh
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
  && curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
sudo nvidia-ctk runtime configure --runtime=containerd
sudo systemctl restart containerd

# To use Docker with GPU in WSL, add `--gpus all`
docker run -it --gpus all ubuntu nvidia-smi

# For CUDA, use
docker run -it --gpus all nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu20.04
docker run -it --gpus all pytorch/pytorch:2.1.2-cuda12.1-cudnn8-devel
```

Notes:

- Run `nvidia-smi` to check hardware, drivers and CUDA version installed.
- [WSL reports /usr/lib/wsl/lib/libcuda.so.1 is not a symbolic link](https://github.com/microsoft/WSL/issues/5663#issuecomment-1068499676)
- [Docker requires /etc/wsl.conf setup](https://github.com/MicrosoftDocs/WSL/issues/1750)
