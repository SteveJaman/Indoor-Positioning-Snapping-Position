import threading
import time
import smtplib
import paho.mqtt.client as mqtt

# For email receipt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import base64
from email.mime.base import MIMEBase
from email import encoders
import json

# Store Stock in dictionary with barcode support and locations
stock = {
    "Preztzel - Mini": {"quantity": 1, "price": 4.99, "barcode": "077975022177", "location": (0.5, 4.5)},
    "Cheez It - Mini": {"quantity": 1, "price": 2.99, "barcode": "024100122615", "location": (2.5, 5.5)},
    "Altoids": {"quantity": 25, "price": 1.99, "barcode": "022000159335", "location": (4.5, 4.5)},
    "90s Crew Sock": {"quantity": 1, "price": 9.95, "barcode": "400427942301", "location": (6.5, 3.5)},
    "Snoopy - Winter": {"quantity": 1, "price": 13.99, "barcode": "193849061827", "location": (6.5,1.5)},
    "Can Corn": {"quantity": 1, "price": 2.58, "barcode": "024000163022", "location": (4.5, 5.5)},
    "Mac & Cheese": {"quantity": 1, "price": 4.99, "barcode": "021000658831", "location": (2.5, 4.5)},
    "Sweet Peas": {"quantity": 1, "price": 3.29, "barcode": "024000163084", "location": (0.5, 1.5)},
    "Test": {"quantity": 999, "price": 999.99, "barcode": "0", "location": (0.5, 0.5)}
}

# Create reverse lookup for barcode
barcode_to_item = {item_data["barcode"]: item_name for item_name, item_data in stock.items()}

# Store pinned items
pinned_items = {}

# Lock for thread-safe access to stock
lock = threading.Lock()

# MQTT Configuration
MQTT_BROKER = "192.168.137.8"  # Your MQTT broker 
MQTT_PORT = 1883
MQTT_ITEM_TOPIC = "indoor/items"
MQTT_COMMANDS_TOPIC = "shopping_app/commands"
MQTT_RESPONSES_TOPIC = "shopping_app/responses"
MQTT_PINNED_TOPIC = "shopping_app/pinned_items"  # New topic for pinned items
MQTT_CLIENT_ID = "Stock_Server"

# MQTT Client
mqtt_client = None
# Store client sessions
client_sessions = {}

##############################################################################################
# MQTT Functions
##############################################################################################
def setup_mqtt():
    """Setup MQTT connection for both publishing and subscribing"""
    global mqtt_client

    mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print(f"MQTT Connected to {MQTT_BROKER}:{MQTT_PORT}")
        print(f"Subscribed to commands topic: {MQTT_COMMANDS_TOPIC}")

        # Publish initial items
        publish_items_update()
        return True

    except Exception as e:
        print(f"MQTT Connection failed: {e}")
        return False

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("MQTT Connected successfully")

        # Subscribe to commands topic
        client.subscribe(MQTT_COMMANDS_TOPIC)
        print(f"Subscribed to {MQTT_COMMANDS_TOPIC}")
    else:
        print(f"Failed to connect to MQTT, return code {rc}")

def on_message(client, userdata, msg):
    """Handle incoming MQTT messages/commands"""
    try:
        topic = msg.topic
        payload = msg.payload.decode()

        if topic == MQTT_COMMANDS_TOPIC:
            print(f"Received command: {payload}")

            # Parse the command
            if ':' in payload:
                client_id, command = payload.split(':', 1)
            else:
                client_id = "default"
                command = payload

            # Process the command in a separate thread
            threading.Thread(target=process_command, args=(client_id, command), daemon=True).start()

    except Exception as e:
        print(f"Error processing MQTT message: {e}")

def send_response(client_id, response):
    """Send response back to client"""
    if mqtt_client and mqtt_client.is_connected():
        response_payload = f"{client_id}:{response}"
        mqtt_client.publish(MQTT_RESPONSES_TOPIC, response_payload)
        print(f"Sent response to client {client_id}")
    else:
        print("MQTT client not connected, cannot send response")

def publish_pinned_item(item_name, barcode, location):
    """Publish pinned item to all clients"""
    if not mqtt_client or not mqtt_client.is_connected():
        print("MQTT not connected, cannot publish pinned item")
        return False

    pinned_message = {
        "type": "item_pinned",
        "item_name": item_name,
        "barcode": barcode,
        "location": location,
        "timestamp": time.time()
    }

    try:
        result = mqtt_client.publish(MQTT_PINNED_TOPIC, json.dumps(pinned_message))
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"ðŸ“ PINNED: Published pinned item {item_name} at {location}")
            return True
        else:
            print(f"âŒ Failed to publish pinned item: {result.rc}")
            return False

    except Exception as e:
        print(f"âŒ Error publishing pinned item: {e}")
        return False

def process_command(client_id, command):
    """Process commands from clients"""
    print(f"Processing command from {client_id}: {command}")

    try:
        if command == "PRICES":
            with lock:
                price_list = "\n".join(f"{item}:{data['price']}" for item, data in stock.items())
            send_response(client_id, price_list)
        elif command == "STOCK":
            with lock:
                stock_list = "\n".join(f"{item}:{data['quantity']}" for item, data in stock.items())
            send_response(client_id, stock_list)
        elif command.startswith("GET_BARCODE:"):
            item_name = command.replace("GET_BARCODE:", "").strip()
            with lock:
                if item_name in stock:
                    barcode = stock[item_name]["barcode"]
                    send_response(client_id, f"BARCODE:{item_name}:{barcode}")
                else:
                    send_response(client_id, f"ERROR:Item {item_name} not found")
        elif command.startswith("GET_ITEM:"):
            barcode = command.replace("GET_ITEM:", "").strip()
            with lock:
                if barcode in barcode_to_item:
                    item_name = barcode_to_item[barcode]
                    price = stock[item_name]["price"]
                    send_response(client_id, f"ITEM:{barcode}:{item_name}:{price}")
                else:
                    send_response(client_id, f"ERROR:Barcode {barcode} not found")

        # NEW: Handle PIN_ITEM command
        elif command.startswith("PIN_ITEM:"):
            parts = command.replace("PIN_ITEM:", "").split(":")
            if len(parts) >= 2:
                item_name = parts[0]
                barcode = parts[1] if len(parts) > 1 else ""
                print(f" PIN request from {client_id}: {item_name} (Barcode: {barcode})")

                # Find the item in stock
                found_item = None
                item_location = None
                with lock:

                    # Try to find by name first
                    if item_name in stock:
                        found_item = item_name
                        item_location = stock[found_item]["location"]

                    # If not found by name, try by barcode
                    elif barcode and barcode in barcode_to_item:
                        found_item = barcode_to_item[barcode]
                        item_location = stock[found_item]["location"]

                    # If barcode is "N/A", try to find by name only
                    elif barcode == "N/A" and item_name in stock:
                        found_item = item_name
                        item_location = stock[found_item]["location"]

                if found_item and item_location:
                    x, y = item_location

                    # Store pinned item
                    pin_id = f"{found_item}_{int(time.time())}"
                    pinned_items[pin_id] = {
                        "item_name": found_item,
                        "barcode": stock[found_item]["barcode"],
                        "location": item_location,
                        "pinned_by": client_id,
                        "timestamp": time.time()
                    }

                    # Send confirmation with location to client
                    send_response(client_id, f"ITEM_PINNED:{found_item}:SUCCESS:Location({x:.1f},{y:.1f})")
                    print(f" Item {found_item} pinned at location ({x:.1f}, {y:.1f})")
                    print(f" SERVER MAP: {found_item} is pinned at coordinates ({x:.1f}, {y:.1f})")

                    # Also publish to all clients via MQTT
                    publish_pinned_item(found_item, stock[found_item]["barcode"], item_location)
                else:
                    send_response(client_id, f"ITEM_PINNED:{item_name}:NOT_FOUND")
                    print(f" Item {item_name} not found in server database")
            else:
                send_response(client_id, "ERROR:Invalid PIN command format")

        elif command.startswith("CHECKOUT"):
            items = command.replace("CHECKOUT", "").strip().split()
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
            send_response(client_id, response)

            if stock_updated:
                print("Stock updated, propagating to indoor positioning...")
                publish_items_update()
        elif command.startswith("RECEIPT"):
            receipt_content = command.replace("RECEIPT", "", 1).strip()
            filename = f"receipt_{client_id}_{int(time.time())}.txt"
            with open(filename, "w") as f:
                f.write(receipt_content)
            send_response(client_id, f"Receipt saved on server as {filename}")
        elif command.startswith("SET_ITEM_LOCATION:"):
            parts = command.replace("SET_ITEM_LOCATION:", "").split(":")
            if len(parts) == 3:
                item_name, x_str, y_str = parts
                try:
                    x = float(x_str)
                    y = float(y_str)
                    with lock:
                        if item_name in stock:
                            stock[item_name]["location"] = (x, y)
                            send_response(client_id, f"Location for {item_name} set to ({x}, {y})")
                            print("Location updated, propagating to indoor positioning...")
                            publish_items_update()
                        else:
                            send_response(client_id, f"ERROR:Item {item_name} not found")
                except ValueError:
                    send_response(client_id, "ERROR:Invalid coordinates")
            else:
                send_response(client_id, "ERROR:Invalid format. Use SET_ITEM_LOCATION:item_name:x:y")

    #Trigeer email   
        elif command.startswith("EMAIL_RECEIPT:"):
            try:
                parts = command.split(":", 2)
                if len(parts) < 3:
                    send_response(client_id, "ERROR:Invalid email receipt format")
                else:
                    email_address = parts[1]
                    pdf_path = parts[2]
            
                # Verify the PDF file exists
                if not os.path.exists(pdf_path):
                    send_response(client_id, f"ERROR:PDF file not found: {pdf_path}")
                    return             

                # Create email content
                subject = "Your CyberKart Receipt"
                body = """Thank you for shopping with CyberKart!
                    Your receipt is attached to this email.

                    Order Details:
                    - Please see the attached PDF for complete order summary
                    - Keep this receipt for your records

                    Thank you for your business!
                    CyberKart Team"""
           
                success = send_email_with_attachment(email_address, subject, body, pdf_path)
                if success:
                    send_response(client_id, f"Receipt with PDF emailed to {email_address}")
                else:
                    send_response(client_id, f"ERROR:Failed to send email to {email_address}")
                    
            except Exception as e:
                send_response(client_id, f"ERROR sending email: {str(e)}")
        elif command == "PROPAGATE_ITEMS":
            print("Manual propagation triggered via client command")
            if publish_items_update():
                send_response(client_id, "Items propagated successfully to indoor positioning system")
            else:
                send_response(client_id, "Failed to propagate items")
        else:
            send_response(client_id, "Unknown command")

    except Exception as e:
        send_response(client_id, f"ERROR processing command: {str(e)}")

def publish_items_update(item_names_to_propagate=None):
    """Publish current items to MQTT topic"""
    if not mqtt_client:
        print("? MQTT client not initialized")
        return False

    if not mqtt_client.is_connected():
        print("? MQTT not connected, attempting to reconnect...")
        try:
            mqtt_client.reconnect()
            time.sleep(1)
        except Exception as e:
            print(f"? Reconnection failed: {e}")
            return False

    try:
        items_to_publish = []     
        with lock:
            if item_names_to_propagate:

                # Propagate only selected items
                for item_name in item_names_to_propagate:
                    if item_name in stock:
                        x, y = stock[item_name]["location"]
                        items_to_publish.append({
                            "name": item_name,
                            "x": x,
                            "y": y
                        })
            else:

                # Propagate all items
                for item_name, data in stock.items():
                    x, y = data["location"]
                    items_to_publish.append({
                        "name": item_name,
                        "x": x,
                        "y": y
                    })

        message = {
            "type": "items_update",
            "items": items_to_publish
        }

        result = mqtt_client.publish(MQTT_ITEM_TOPIC, json.dumps(message))      

        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"? Published {len(items_to_publish)} items to {MQTT_ITEM_TOPIC}")
            return True
        else:

            print(f"? Failed to publish items: {result.rc}")

            return False

            

    except Exception as e:

        print(f"? Error publishing items: {e}")

        return False

        

    # ... rest of your existing code ...



##############################################################################################

# Receipt System

##############################################################################################



# def send_email(receiver_email, receipt_content):

#     sender_email = "ctspi2025@gmail.com"

#     sender_password = "bdst xvqu dmqm gpdq"



#     msg = MIMEMultipart()

#     msg["From"] = sender_email

#     msg["To"] = receiver_email

#     msg["Subject"] = "Your Receipt"



#     msg.attach(MIMEText(receipt_content, "plain"))



#     try:

#         with smtplib.SMTP("smtp.gmail.com", 587) as server:

#             server.starttls()

#             server.login(sender_email, sender_password)

#             server.sendmail(sender_email, receiver_email, msg.as_string())

#         print(f"[EMAIL] Receipt sent to {receiver_email}")

#         return True

#     except Exception as e:

#         print(f"[EMAIL ERROR] {e}")

#         return False



def send_email_with_attachment(receiver_email, subject, body, pdf_path=None):

    sender_email = "ctspi2025@gmail.com"

    sender_password = "bdst xvqu dmqm gpdq"



    msg = MIMEMultipart()

    msg["From"] = sender_email

    msg["To"] = receiver_email

    msg["Subject"] = subject



    # Add email body

    msg.attach(MIMEText(body, "plain"))



    # Add PDF attachment if provided

    if pdf_path and os.path.exists(pdf_path):

        try:

            with open(pdf_path, "rb") as attachment:

                part = MIMEBase("application", "octet-stream")

                part.set_payload(attachment.read())

            

            encoders.encode_base64(part)

            part.add_header(

                "Content-Disposition",

                f"attachment; filename= {os.path.basename(pdf_path)}",

            )

            msg.attach(part)

            print(f"[EMAIL] PDF attachment added: {pdf_path}")

        except Exception as e:

            print(f"[EMAIL ERROR] Failed to attach PDF: {e}")



    try:

        with smtplib.SMTP("smtp.gmail.com", 587) as server:

            server.starttls()

            server.login(sender_email, sender_password)

            server.sendmail(sender_email, receiver_email, msg.as_string())

        print(f"[EMAIL SUCCESS] Receipt with attachment sent to {receiver_email}")

        return True

    except Exception as e:

        print(f"[EMAIL ERROR] {e}")

        return False



#############################################################################################

# Command Loop

#############################################################################################



def command_loop():

    """Runs on the server host to control stock."""

    while True:

        cmd = input(

            "\nEnter command (show | add <item> <qty> <barcode> | subtract <item> <qty> | "

            "set_price <item> <price> | set_location <item> <x> <y> | "

            "propagate | propagate_selected <item1> [item2]... | pinned | help): ").strip().split()

        if not cmd:

            continue



        command = cmd[0].lower()



        if command == "show":

            with lock:

                print("\n" + "=" * 80)

                print("CURRENT STOCK AND LOCATIONS")

                print("=" * 80)

                for item, data in stock.items():

                    x, y = data["location"]

                    print(f"â”‚ {item:15} â”‚ Qty: {data['quantity']:3} â”‚ Price: ${data['price']:6.2f} â”‚ "

                          f"Barcode: {data['barcode']:12} â”‚ Location: ({x:.1f}, {y:.1f}) â”‚")

                print("=" * 80)



        elif command == "pinned":

            print("\n" + "=" * 60)

            print("PINNED ITEMS")

            print("=" * 60)

            if pinned_items:

                for pin_id, pin_data in pinned_items.items():

                    x, y = pin_data["location"]

                    time_str = time.strftime("%H:%M:%S", time.localtime(pin_data["timestamp"]))

                    print(f" {pin_data['item_name']:15} â”‚ Location: ({x:.1f}, {y:.1f}) â”‚ "

                          f"By: {pin_data['pinned_by']:10} â”‚ Time: {time_str}")

            else:

                print("No items currently pinned")

            print("=" * 60)



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

            print("\n" + "=" * 60)

            print("STOCK SERVER COMMANDS")

            print("=" * 60)

            print("show                    - Display all items with locations")

            print("pinned                  - Show currently pinned items")

            print("add <item> <qty> [barcode] - Add quantity to existing item or create new")

            print("subtract <item> <qty>   - Remove quantity from item")

            print("set_price <item> <price> - Set item price")

            print("set_location <item> <x> <y> - Set item coordinates")

            print("propagate               - MANUALLY send items to indoor positioning")

            print("help                    - Show this help message")

            print("\nItems auto-propagate on: add, subtract, set_location")

            print("Use 'propagate' to manually send current items")

            print("=" * 60)



        else:

            print("Unknown command. Type 'help' for available commands.")





##############################################################################################

# Main Server

##############################################################################################



def start_server():

    """Start the MQTT-based server"""

    print("Starting MQTT Stock Server with Indoor Positioning Integration...")

    print(f"MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")

    print(f"Commands topic: {MQTT_COMMANDS_TOPIC}")

    print(f"Responses topic: {MQTT_RESPONSES_TOPIC}")

    print(f"Items topic: {MQTT_ITEM_TOPIC}")

    print(f"Pinned items topic: {MQTT_PINNED_TOPIC}")



    if not setup_mqtt():

        print("Failed to connect to MQTT broker. Exiting.")

        return



    print(f"[LISTENING] MQTT Server started")

    print(f"[INFO] Type 'help' for available commands")

    print("-" * 60)



    command_loop()  # Run stock control loop in main thread





if __name__ == "__main__":

    start_server()

