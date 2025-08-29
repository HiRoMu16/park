# ROS 2 Humble + Desktop + Gazeboを含む公式イメージをベースにする
FROM osrf/ros:humble-desktop-full

# 環境変数を設定
ENV SHELL /bin/bash

# 必要なパッケージをインストール
RUN apt-get update && apt-get install -y \
    git \
    vim \
    wget \
    bash-completion \
    ros-dev-tools \
    # TurtleBot3関連
    ros-humble-turtlebot3* \
    # SLAM/Navigation関連
    ros-humble-slam-toolbox \
    ros-humble-navigation2 \
    ros-humble-nav2-bringup \
    # Gazebo連携
    ros-humble-gazebo-ros-pkgs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# VS Codeが使用する非rootユーザーを作成
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# ROS環境を自動で読み込むように設定
RUN echo "source /opt/ros/humble/setup.bash" >> /home/$USERNAME/.bashrc
RUN echo "source /usr/share/colcon_cd/function/colcon_cd.sh" >> /home/$USERNAME/.bashrc
RUN echo "export _colcon_cd_root=~/workspaces/ros2-web-slam/ros2_ws" >> /home/$USERNAME/.bashrc

# ユーザーをvscodeに変更
USER $USERNAME