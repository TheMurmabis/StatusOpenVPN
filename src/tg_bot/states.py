"""Состояния FSM для Telegram-бота."""

from aiogram.fsm.state import State, StatesGroup


class VPNSetup(StatesGroup):
    """Состояния процессов управления VPN."""
    
    choosing_option = State()
    entering_client_name = State()
    entering_days = State()
    deleting_client = State()
    list_for_delete = State()
    choosing_config_type = State()
    choosing_protocol = State()
    choosing_wg_type = State()
    confirming_rename = State()
    entering_client_mapping = State()
    entering_cpu_threshold = State()
    entering_memory_threshold = State()
    entering_request_client_name = State()
