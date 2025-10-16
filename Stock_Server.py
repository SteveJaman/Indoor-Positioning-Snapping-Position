import socket
import threading
import time
import smtplib
import paho.mqtt.client as mqtt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

# Store Stock in dictionary with barcode support and locations
stock = {
    "Drink": {"quantity": 30, "price": 1.50, "barcode": "12434", "location": (1.0, 4.0)},
    "Snack": {"quantity": 50, "price": 20.99, "barcode": "9876", "location": (2.0, 5.0)},
    "Altoid": {"quantity": 25, "price": 0.01, "barcode": "022000159335", "location": (3.0, 3.0)}
}

# Create reverse lookup for barcode
barcode_to_item = {item_data["barcode"]: item_name for item_name, item_data in stock.items()}

# Lock for thread-safe access to stock
lock = threading.Lock()

# MQTT Configuration
MQTT_BROKER = "10.19.148.3"  # Your MQTT broker IP
MQTT_PORT = 1883
MQTT_ITEM_TOPIC = "indoor/items"
MQTT_CLIENT_ID = "Stock_Server"

# MQTT Client
mqtt_client = None

##############################################################################################
# MQTT Functions
##############################################################################################

def setup_mqtt():
    """Setup MQTT connection for publishing item updates"""
    global mqtt_client
    
    mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print(f"MQTT Connected to {MQTT_BROKER}:{MQTT_PORT}")
        # Publish initial items
        publish_items_update()
        return True
    except Exception as e:
        print(f"MQTT Connection failed: {e}")
        return False

def publish_items_update(item_names_to_propagate=None):
    """Publish current items to MQTT topic"""
    if not mqtt_client or not mqtt_client.is_connected():
        print("MQTT not connected, cannot publish items")
        return False
    
    with lock:
        items_data = []

        items_to_check = item_names_to_propagate if item_names_to_propagate is not None else stock.keys()

        for item_name in items_to_check:
            if item_name in stock:
                item_data = stock[item_name]

                if item_data["quantity"] > 0:
                    x, y = item_data["location"]
                    items_data.append({
                        "name": item_name,
                        "x": x,
                        "y": y,
                        "quantity": item_data["quantity"],
                        "price": item_data["price"],
                        "barcode": item_data["barcode"]
                    })
    
    message = json.dumps({
        "type": "items_update",
        "timestamp": time.time(),
        "items": items_data
    })
    
    try:
        result = mqtt_client.publish(MQTT_ITEM_TOPIC, message)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"MQTT Published {len(items_data)} items to {MQTT_ITEM_TOPIC}")
            print(f"   Items: {[item['name'] for item in items_data]}")
            return True
        else:
            print(f"MQTT Publish failed with code: {result.rc}")
            return False
    except Exception as e:
        print(f"MQTT Publish error: {e}")
        return False

##############################################################################################
# Receipt System
##############################################################################################

def send_email(receiver_email, receipt_content):
    sender_email = "ctspi2025@gmail.com"
    sender_password = "bdst xvqu dmqm gpdq"

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = "Your Receipt"

    msg.attach(MIMEText(receipt_content, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        print(f"[EMAIL] Receipt sent to {receiver_email}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False

##############################################################################################
# Client Handler
##############################################################################################

def handle_client(conn, addr):
    print(f"[CONNECTED] {addr}")
    
    with conn:
        while True:
            try:
                data = conn.recv(1024).decode().strip()
                if not data:
                    break

                if data.startswith("CHECKOUT"):
                    items = data.replace("CHECKOUT", "").strip().split()
                    response_lines = []
                    stock_updated = False
                    
                    with lock:
                        for entry in items:
                            try:
                                if ":" in entry:
                                    identifier, qty = entry.split(":")
                                    qty = int(qty)

                                    if identifier in barcode_to_item:
                                        item_name = barcode_to_item[identifier]
                                    else:
                                        item_name = identifier

                                    if item_name in stock and stock[item_name]["quantity"] >= qty:
                                        stock[item_name]["quantity"] -= qty
                                        response_lines.append(
                                            f"Deducted {qty} {item_name}(s). Remaining: {stock[item_name]['quantity']}")
                                        stock_updated = True
                                    else:
                                        response_lines.append(f"Not enough {item_name} in stock.")
                                else:
                                    response_lines.append(f"Invalid format: {entry}")

                            except Exception as e:
                                response_lines.append(f"Error processing {entry}: {str(e)}")

                    response = "\n".join(response_lines)
                    conn.sendall(response.encode())
                    
                    if stock_updated:
                        print("Stock updated, propagating to indoor positioning...")
                        publish_items_update()

                elif data == "PRICES":
                    with lock:
                        price_list = "\n".join(f"{item}:{data['price']}" for item, data in stock.items())
                    conn.sendall(price_list.encode())

                elif data.startswith("GET_BARCODE:"):
                    item_name = data.replace("GET_BARCODE:", "").strip()
                    with lock:
                        if item_name in stock:
                            barcode = stock[item_name]["barcode"]
                            conn.sendall(f"BARCODE:{item_name}:{barcode}".encode())
                        else:
                            conn.sendall(f"ERROR:Item {item_name} not found".encode())

                elif data.startswith("GET_ITEM:"):
                    barcode = data.replace("GET_ITEM:", "").strip()
                    with lock:
                        if barcode in barcode_to_item:
                            item_name = barcode_to_item[barcode]
                            price = stock[item_name]["price"]
                            conn.sendall(f"ITEM:{barcode}:{item_name}:{price}".encode())
                        else:
                            conn.sendall(f"ERROR:Barcode {barcode} not found".encode())

                elif data.startswith("RECEIPT"):
                    receipt_content = data.replace("RECEIPT", "", 1).strip()
                    filename = f"receipt_{addr[0]}_{addr[1]}_{int(time.time())}.txt"
                    with open(filename, "w") as f:
                        f.write(receipt_content)
                    conn.sendall(f"Receipt saved on server as {filename}".encode())

                elif data == "STOCK":
                    with lock:
                        stock_list = "\n".join(f"{item}:{data['quantity']}" for item, data in stock.items())
                    conn.sendall(stock_list.encode())

                elif data.startswith("SET_ITEM_LOCATION:"):
                    parts = data.replace("SET_ITEM_LOCATION:", "").split(":")
                    if len(parts) == 3:
                        item_name, x_str, y_str = parts
                        try:
                            x = float(x_str)
                            y = float(y_str)
                            with lock:
                                if item_name in stock:
                                    stock[item_name]["location"] = (x, y)
                                    conn.sendall(f"Location for {item_name} set to ({x}, {y})".encode())
                                    print("Location updated, propagating to indoor positioning...")
                                    publish_items_update()
                                else:
                                    conn.sendall(f"ERROR:Item {item_name} not found".encode())
                        except ValueError:
                            conn.sendall("ERROR:Invalid coordinates".encode())
                    else:
                        conn.sendall("ERROR:Invalid format. Use SET_ITEM_LOCATION:item_name:x:y".encode())

                elif data == "PROPAGATE_ITEMS":
                    # NEW: Manual command to propagate items to indoor positioning
                    print("Manual propagation triggered via client command")
                    if publish_items_update():
                        conn.sendall("Items propagated successfully to indoor positioning system".encode())
                    else:
                        conn.sendall("Failed to propagate items".encode())

                else:
                    conn.sendall("Server received your message.".encode())

            except ConnectionResetError:
                break
    
    print(f"[DISCONNECTED] {addr}")

#############################################################################################
# Command Loop
#############################################################################################

def command_loop():
    """Runs on the server host to control stock."""
    while True:
        cmd = input(
            "\nEnter command (show | add <item> <qty> <barcode> | subtract <item> <qty> | "
            "set_price <item> <price> | set_location <item> <x> <y> | "
            "propagate | propagate_selected <item1> [item2]... | help): ").strip().split()
        if not cmd:
            continue

        command = cmd[0].lower()

        if command == "show":
            with lock:
                print("\n" + "="*80)
                print("CURRENT STOCK AND LOCATIONS")
                print("="*80)
                for item, data in stock.items():
                    x, y = data["location"]
                    print(f"│ {item:15} │ Qty: {data['quantity']:3} │ Price: ${data['price']:6.2f} │ "
                          f"Barcode: {data['barcode']:12} │ Location: ({x:.1f}, {y:.1f}) │")
                print("="*80)

        elif command == "add" and len(cmd) >= 3:
            item = cmd[1]
            try:
                qty = int(cmd[2])
                if len(cmd) >= 4:
                    barcode = cmd[3]
                else:
                    barcode = "000000000000"
            except ValueError:
                print("Invalid quantity.")
                continue

            with lock:
                if item in stock:
                    stock[item]["quantity"] += qty
                    print(f"Added {qty} {item}(s). New quantity: {stock[item]['quantity']}")
                else:
                    default_location = (len(stock) + 1.0, len(stock) + 1.0)
                    stock[item] = {"quantity": qty, "price": 0.0, "barcode": barcode, "location": default_location}
                    barcode_to_item[barcode] = item
                    print(f"Created {qty} {item}(s). Barcode: {barcode}, Location: {default_location}")
            
            print("Auto-propagating to indoor positioning...")
            publish_items_update()

        elif command == "subtract" and len(cmd) == 3:
            item = cmd[1]
            try:
                qty = int(cmd[2])
            except ValueError:
                print("Invalid quantity.")
                continue

            with lock:
                if item in stock:
                    if stock[item]["quantity"] >= qty:
                        stock[item]["quantity"] -= qty
                        print(f"Removed {qty} {item}(s). New quantity: {stock[item]['quantity']}")
                        print("Auto-propagating to indoor positioning...")
                        publish_items_update()
                    else:
                        print(f"Not enough {item} in stock. Current quantity: {stock[item]['quantity']}")
                else:
                    print(f"Item {item} not found.")

        elif command == "set_price" and len(cmd) == 3:
            item = cmd[1]
            try:
                price = float(cmd[2])
            except ValueError:
                print("Invalid price.")
                continue

            with lock:
                if item in stock:
                    stock[item]["price"] = price
                    print(f"Set price for {item} to ${price}")
                else:
                    print(f"Item {item} not found.")

        elif command == "set_location" and len(cmd) == 4:
            item = cmd[1]
            try:
                x = float(cmd[2])
                y = float(cmd[3])
            except ValueError:
                print("Invalid coordinates.")
                continue

            with lock:
                if item in stock:
                    stock[item]["location"] = (x, y)
                    print(f"Set location for {item} to ({x}, {y})")
                    print("Auto-propagating to indoor positioning...")
                    publish_items_update()
                else:
                    print(f"Item {item} not found.")

        elif command == "propagate":
            # NEW: Manual command to propagate items
            print("Manually propagating items to indoor positioning system...")
            if publish_items_update():
                print("Items propagated successfully!")
            else:
                print("Failed to propagate items")
                
        elif command == "propagate_selected" and len(cmd) > 1:
            items_to_propagate = cmd[1:]
            valid_items = [item for item in items_to_propagate if item in stock]

            if not valid_items:
                print("No valid items selected for propagations.")
                continue

            print(f"Manually propagating selected items: {', '.join(valid_items)}...")

            if publish_items_update(valid_items):
                print("Selected items propagated successfully!")
            else:
                print("Failed to propagate selected items.")

        elif command == "help":
            print("\n" + "="*60)
            print("STOCK SERVER COMMANDS")
            print("="*60)
            print("show                    - Display all items with locations")
            print("add <item> <qty> [barcode] - Add quantity to existing item or create new")
            print("subtract <item> <qty>   - Remove quantity from item")
            print("set_price <item> <price> - Set item price")
            print("set_location <item> <x> <y> - Set item coordinates")
            print("propagate               - MANUALLY send items to indoor positioning")
            print("help                    - Show this help message")
            print("\Items auto-propagate on: add, subtract, set_location")
            print("Use 'propagate' to manually send current items")
            print("="*60)

        else:
            print("Unknown command. Type 'help' for available commands.")

##############################################################################################
# Main Server
##############################################################################################

def start_server(host="10.19.148.202", port=1883):  # UPDATED: Your new IP address
    # Setup MQTT first
    print("Starting Stock Server with Indoor Positioning Integration...")
    print(f"Server IP: {host}")
    print(f"Port: {port}")
    
    if not setup_mqtt():
        print("Starting without MQTT - item updates won't be published to positioning system")
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((host, port))
    server.listen()

    print(f"[LISTENING] Server started on {host}:{port}")
    print(f"[MQTT] Item propagation topic: {MQTT_ITEM_TOPIC}")
    print(f"[INFO] Type 'help' for available commands")
    print("-" * 60)

    # Thread to accept clients
    def accept_clients():
        while True:
            conn, addr = server.accept()
            thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
            thread.start()

    threading.Thread(target=accept_clients, daemon=True).start()
    command_loop()  # Run stock control loop in main thread

if __name__ == "__main__":
    start_server()