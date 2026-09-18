import json
import logging
import subprocess
import time
from pathlib import Path


class TemplateDialogueBackend:
    def generate(self, facts, player_text=""):
        return facts.get("canonical", "Stay on the permitted outdoor path. What would you like to do?")


def available_mb():
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            if line.startswith('MemAvailable:'):
                return int(line.split()[1])/1024
    except OSError:
        pass
    return 0


class LlamaCppDialogueBackend:
    """An ephemeral CLI process bounds RAM lifetime and supports a real kill timeout."""
    def __init__(self,cfg,gate):
        self.cfg,self.gate = cfg,gate
        self.fallback = TemplateDialogueBackend()
        self.latency_ms = 0

    def generate(self,facts,player_text=""):
        fallback = self.fallback.generate(facts,player_text)
        if not self.cfg["llm_enabled"] or available_mb() < self.cfg["min_available_mb"]:
            return fallback
        prompt = ('You are an RPG NPC. Reply in at most three short sentences. Only paraphrase canonical text. '
                  'Never invent places, items, characters, quests, actions or travel instructions. '
                  'WORLD FACTS: '+json.dumps(facts,ensure_ascii=False)+'\nPLAYER: '+player_text[:256]+'\nNPC:')
        start = time.monotonic()
        try:
            with self.gate.lock:
                output = subprocess.run([self.cfg["executable"],"-m",self.cfg["model"],"-c",str(self.cfg["max_context"]),
                    "-n",str(self.cfg["max_output_tokens"]),"-p",prompt,"--no-display-prompt"],capture_output=True,text=True,timeout=self.cfg["timeout_sec"],check=True).stdout.strip()
            # Conservative closed vocabulary prevents ungrounded new game entities/instructions.
            # Richer wording requires a separately validated local model/output policy.
            allowed = set(fallback.lower().replace('.','').replace('?','').split())
            words = set(output.lower().replace('.','').replace('?','').split())
            if not output or len(output)>400 or not words.issubset(allowed) or output.count('.')+output.count('?')>3:
                return fallback
            return output
        except (OSError,subprocess.SubprocessError):
            logging.getLogger("NPC").warning("llm_fallback")
            return fallback
        finally:
            self.latency_ms = (time.monotonic()-start)*1000
