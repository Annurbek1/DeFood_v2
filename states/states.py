from aiogram.fsm.state import State, StatesGroup

class OrderState(StatesGroup):

    selecting_restaurant = State()
    viewing_restaurant_menu = State()
    selecting_category = State()
    viewing_category_items = State()
    

    selecting_food = State()
    viewing_food_details = State()
    

    viewing_cart = State()
    viewing_cart_to_restaurant = State()
    adding_food_to_cart = State()
    editing_cart = State()
    removing_from_cart = State()
    confirming_cart = State()
    

    selecting_delivery_address = State()
    adding_address = State()
    editing_address = State()
    waiting_for_address = State()
    waiting_for_address_name = State()
    adding_new_address_location = State()
    waiting_cancel_reason = State()
    adding_new_address_name = State()
    confirming_address = State()
    confirming_new_address = State()
    waiting_restaurant_message = State()
    waiting_delivery_message = State()
    confirming_order = State()
    
    
    adding_phone = State()
    editing_phone = State()
    waiting_for_phone = State()
    confirming_phone = State()
    waiting_restaurant_message = State()
    writing_restaurant_message = State()
    
    handle_new_address_location = State()
    handle_new_address_name = State()
    editing_address_location = State()
    editing_address_name = State()

    creating_order = State()
    confirming_order = State()
    viewing_orders = State()
    reviewing_order = State()
    

    waiting_for_delivery = State()
    delivery_in_progress = State()
    confirming_delivery = State()
    

    viewing_settings = State()
    editing_settings = State()