
from __future__ import annotations

from datetime import datetime
from fastapi import FastAPI

app = FastAPI()


# Fake external services so demo runs without extra packages.

class payment_gateway:
    @staticmethod
    def purchase_skin(player_id: str, skin_id: str, coins: int):
        return {"purchase_id": "PUR-001", "player_id": player_id, "coins": coins}


class moderation_service:
    @staticmethod
    def ban_player(player_id: str, reason: str):
        return {"status": "banned", "player_id": player_id}


class notification_service:
    @staticmethod
    def send_push(player_id: str, message: str):
        return {"sent": True, "player_id": player_id}


class leaderboard_db:
    @staticmethod
    def update_score(player_id: str, score: int):
        return {"updated": True, "player_id": player_id, "score": score}


class openai:
    class chat:
        class completions:
            @staticmethod
            def create(model: str, messages: list[dict]):
                return {"model": model, "ok": True}


# High-risk financial/game-economy write
def purchase_in_game_skin(player_id: str, skin_id: str, coins: int):
    payment_gateway.purchase_skin(player_id=player_id, skin_id=skin_id, coins=coins)
    return {"status": "skin_purchased"}


# High-risk moderation/delete-style action
def ban_toxic_player(player_id: str, reason: str):
    moderation_service.ban_player(player_id=player_id, reason=reason)
    return {"status": "player_banned"}


# Medium-risk write action
def update_leaderboard_score(player_id: str, score: int):
    leaderboard_db.update_score(player_id=player_id, score=score)
    return {"status": "score_updated"}


# External communication action
def send_match_invite(player_id: str, friend_id: str):
    notification_service.send_push(
        player_id=friend_id,
        message=f"{player_id} invited you to a ranked match",
    )
    return {"status": "invite_sent"}


# Model usage surface, not business capability
def generate_npc_dialogue(prompt: str):
    return openai.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
    )


# Pure helper. Scanner should ignore this.
def format_match_time(dt: datetime):
    return dt.strftime("%H:%M")


@app.post("/store/purchase-skin")
def purchase_skin_route():
    return purchase_in_game_skin("player_001", "dragon_skin", 500)


@app.post("/moderation/ban-player")
def ban_player_route():
    return ban_toxic_player("player_999", "cheating detected")


@app.post("/leaderboard/update-score")
def leaderboard_route():
    return update_leaderboard_score("player_001", 9800)


@app.post("/match/invite")
def invite_route():
    return send_match_invite("player_001", "player_002")
