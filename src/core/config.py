# src/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional, Dict

class Settings(BaseSettings):
    TOKEN: str
    DATABASE_URL: str = ""  
    PREFIX: str = "!"
    EXTENSIONS: List[str] = [
        #"src.tests.test_embed",
        "src.cogs.moderation",
        "src.cogs.economy",
        "src.cogs.clans",
        "src.cogs.love",
        "src.cogs.ticket",
        "src.cogs.help_commands",
        #"src.cogs.developer",
    ]

    moderator_command_clear: List[int] = [1328296146682122250, 1328294472315961478, 1328294472286736427, 1328293768033599549, 1328293948686598238, 1328290182973358171, 1356239811262025968]

    moderator_command_warn: List[int] = []
    moderator_command_warn_remove: List[int] = []
    moderator_command_strike: List[int] = []
    moderator_command_praise: List[int] = []
    moderator_command_discipline_view: List[int] = []
    #moderator_command_ban: List[int] = []
    moderator_command_moderate: List[int] = [1328296146682122250, 1328294472315961478, 1328294472286736427, 1328293768033599549, 1328293948686598238, 1328290182973358171, 1356239811262025968]

    moderator_display_roles: List[int] = [1426439438296416277]

    TEST_GUILD_ID: Optional[int] = 1327946537061453896

    TEXT_MUTE_ROLE_ID: int = 1356287472467710093
    VOICE_MUTE_ROLE_ID: int = 1356287644740489286

    log_channel_moderation_id: Optional[int] = 1327982816662655046

    ECONOMY_SYMBOL: str = "<:money:1426635893136953444>"
    ECONOMY_WEEKLY_ENABLED: bool = True
    ECONOMY_DAILY_AMOUNT: int = 100
    ECONOMY_WORK_AMOUNT: int = 150
    ECONOMY_WEEKLY_AMOUNT: int = 200
    ECONOMY_DAILY_COOLDOWN_SECONDS: int = 86400
    ECONOMY_WORK_COOLDOWN_SECONDS: int = 3600
    ECONOMY_WEEKLY_COOLDOWN_SECONDS: int = 604800
    ECONOMY_CUSTOM_ROLE_PRICE: int = 50000
    ECONOMY_CUSTOM_ROLE_MONTHLY_PRICE: int = 5000
    ECONOMY_REVIEW_CHANNEL_ID: Optional[int] = 1404197914909081782
    ECONOMY_REVIEW_ROLES: List[int] = [1328293768033599549, 1328293948686598238, 1328290182973358171]
    ECONOMY_ADMIN_ROLES: List[int] = [1328293768033599549, 1328293948686598238, 1328290182973358171]
    
    ECONOMY_ROB_MIN_AMOUNT: int = 300
    ECONOMY_ROB_MAX_AMOUNT: int = 1000
    
    ECONOMY_CASES: List[dict] = [
    {
    "name": "Обычный кейс",
    "description": "Базовый кейс с небольшими наградами",
    "price": 500,
    "rewards": [
                 {
                     "type": "money",
                     "name": "Маленький выигрыш",
                     "amount": 300,
                     "chance": 50,
                     "rarity": "Обычная"
                 },
                 {
                     "type": "money",
                     "name": "Средний выигрыш",
                     "amount": 700,
                     "chance": 30,
                     "rarity": "Необычная"
                },
                 {
                     "type": "xp",
                     "name": "Бонус опыта",
                     "xp": 100,
                     "chance": 15,
                     "rarity": "Редкая"
                },
                {
                    "type": "role",
                    "name": "VIP роль на день",
                    "role_id": 1426648794375917679,
                    "duration_seconds": 86400,
                    "chance": 5,
                    "rarity": "Легендарная"
                }
    ]
    },
    ]
    
    ECONOMY_JOBS: List[dict] = [
        {
            "name": "Разносчик газет",
            "description": "Доставка газет по утрам",
            "min_reward": 10,
            "max_reward": 30
        },
        {
            "name": "Официант",
            "description": "Работа в ресторане",
            "min_reward": 20,
            "max_reward": 40
        },
        {
            "name": "Курьер",
            "description": "Доставка посылок",
            "min_reward": 30,
            "max_reward": 50
        },
        {
            "name": "Продавец",
            "description": "Работа в магазине",
            "min_reward": 50,
            "max_reward": 75
        },
        {
            "name": "Водитель такси",
            "description": "Перевозка пассажиров",
            "min_reward": 50,
            "max_reward": 90
        },
        {
            "name": "Программист",
            "description": "Разработка программного обеспечения",
            "min_reward": 100,
            "max_reward": 200
        },
        {
            "name": "Дизайнер",
            "description": "Создание графических материалов",
            "min_reward": 100,
            "max_reward": 200
        },
        {
            "name": "Переводчик",
            "description": "Перевод документов",
            "min_reward": 60,
            "max_reward": 100
        }
    ]
    
    ECONOMY_XP_SOURCES: Dict[str, float] = {
        "message": 0.5,
        "voice_minute": 0.5,
    }
    
    # Если пустой, используется формула: level * 100
    ECONOMY_XP_PER_LEVEL: Dict[int, int] = {
        1: 100,
        2: 200,
        3: 300,
        4: 400,
        5: 500,
        6: 600,
        7: 700,
        8: 800,
        9: 900,
        10: 1000,
        11: 1100,
        12: 1200,
        13: 1300,
        14: 1400,
        15: 1500,
        16: 1600,
        17: 1700,
        18: 1800,
        19: 1900,
        20: 2000,
        21: 2100,
        22: 2200,
        23: 2300,
        24: 2400,
        25: 2500,
        26: 2600,
        27: 2700,
        28: 2800,
        29: 2900,
        30: 3000,
    }
    
    CLAN_INFO_CHANNEL_ID: Optional[int] = 1430952566031777888
    CLAN_CREATE_COST: int = 100000 
    CLAN_MONTHLY_COST: int = 5000  
    CLAN_OWNER_ROLE_ID: Optional[int] = 1430952817010409567
    CLAN_TEXT_CATEGORY_ID: Optional[int] = 1430952456623358085
    CLAN_VOICE_CATEGORY_ID: Optional[int] = 1430953151137058816
    CLAN_FOR_OWNER_CHANNEL_ID: Optional[int] = 1430952801990873168 
    CLAN_DEFAULT_MAX_MEMBERS: int = 10
    CLAN_MEMBER_SLOT_COST: int = 10000  
    CLAN_VOICE_CHANNEL_COST: int = 5000 
    CLAN_MAX_VOICE_CHANNELS: int = 3  
    CLAN_MAX_MEMBER_SLOTS: int = 50  


    LOVE_CATEGORY_ID: int = 1429502354633523371 
    LOVE_VOICE_CHANNEL_ID: int = 1430190684861632623
    LOVE_MARRY_COST: int = 1000  
    LOVE_ROOM_ACCESS_COST: int = 5000  

    TICKET_STAFF_APPLICATION_IMAGE: str = "https://i.ibb.co/0pP8Q78b/image.png"  
    TICKET_SUPPORT_IMAGE: str = "https://i.ibb.co/Csn9Sn5h/image.png"  
    
    TICKET_SERVER_APPEAL_ROLES: List[int] = [1328297607516127304, 1328296146682122250]  
    TICKET_MODERATION_APPEAL_ROLES: List[int] = [1328293768033599549] 
    TICKET_TECH_SUPPORT_ROLES: List[int] = [1328293948686598238] 
    TICKET_STAFF_APPLICATION_ROLES: List[int] = [1328290182973358171, 1328294472315961478] 

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

settings = Settings()
