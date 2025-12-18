sudo apt install -y python3 python3-venv curl
source monitor_sc_env/bin/activate
pip install textual psutil requests
python3 monitor-sc.py mode --manual
