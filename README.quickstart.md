# Quickstart

1) `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`  
2) `cp .env.example .env` and edit credentials  
3) Test one-shot: `python poller.py --once`  
4) Start exporter: `python exporter.py` and visit `http://localhost:9108/metrics`  

Troubleshooting:
- If Genie parse fails, ensure `pyats` and `genie.libs.parser` versions align.
- Some platforms need `| json` enabled or NX-API/CLI JSON support.