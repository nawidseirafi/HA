cd /opt/ai-agent
source venv/bin/activate
pip install google-genai openai

cd /opt/ai-agent
source venv/bin/activate
python main.py
tail -n 50 /opt/ai-agent/logs/agent-api.log
