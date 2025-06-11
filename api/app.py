from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

app = Flask(__name__)
CORS(app) # Ito ay importante para makapag-communicate ang frontend mo sa backend

# Load environment variables from .env file
load_dotenv()

# Database configuration from environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')

# Helper function para sa ligtas na pag-evaluate ng simpleng arithmetic expressions
def safe_eval_arithmetic_expression(expr):
    """
    Evaluates simple arithmetic expressions (multiplication, addition, subtraction).
    Converts 'x' or '×' to '*' for evaluation.
    Handles single numbers directly.
    """
    expr = str(expr).strip()
    if not expr:
        return 0

    # Replace multiplication symbols for Python's eval
    expr = expr.replace('×', '*').replace('x', '*')

    # Basic validation to prevent arbitrary code execution
    # This is a simple whitelist; for complex scenarios, a proper parser is needed.
    allowed_chars = "0123456789*+-."
    if not all(c in allowed_chars for c in expr):
        raise ValueError(f"Invalid characters in expression: {expr}")

    try:
        return eval(expr)
    except (SyntaxError, NameError, TypeError, ZeroDivisionError) as e:
        raise ValueError(f"Error evaluating expression '{expr}': {e}")

# Function para kumonekta sa database
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# Function para i-check o i-create ang table
def check_or_create_table():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS inventory_items (
                id SERIAL PRIMARY KEY,
                item_code TEXT NOT NULL UNIQUE,
                breakdown TEXT,
                remarks TEXT
            );
        """)
        conn.commit()
        print("Database table 'inventory_items' checked/created successfully.")
    except Exception as e:
        print(f"Error checking/creating table: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

# Run this function when the app starts
with app.app_context():
    check_or_create_table()

@app.route('/update_inventory', methods=['POST'])
def update_inventory():
    data = request.json
    current_breakdown_str = data.get('breakdown', '')
    current_remarks_str = data.get('remarks', '')
    deduct_amount_raw = data.get('deduct_amount', '0')
    item_code = data.get('item_code', '').strip()

    # Convert deduct_amount to a numeric value
    try:
        deduct_amount = float(deduct_amount_raw)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid deduction amount."}), 400

    if deduct_amount <= 0:
        return jsonify({"status": "error", "message": "Deduction amount must be positive."}), 400

    current_breakdown_parts = [p.strip() for p in current_breakdown_str.split('|')] if current_breakdown_str else []
    current_remarks_parts = [r.strip() for r in current_remarks_str.split('|')] if current_remarks_str else []

    # Ensure remarks match breakdown parts, fill with empty string if missing
    while len(current_remarks_parts) < len(current_breakdown_parts):
        current_remarks_parts.append("")

    new_breakdown_parts = list(current_breakdown_parts)
    new_remarks_parts = list(current_remarks_parts)

    deducted_amount = deduct_amount

    for i in range(len(new_breakdown_parts)):
        try:
            current_part_value = safe_eval_arithmetic_expression(new_breakdown_parts[i])
        except ValueError as e:
            return jsonify({"status": "error", "message": f"Invalid breakdown expression: {e}"}), 400

        if deducted_amount <= 0:
            break

        if current_part_value >= deducted_amount:
            remaining_in_part = current_part_value - deducted_amount
            new_breakdown_parts[i] = str(remaining_in_part) if remaining_in_part != 0 else "0"
            deducted_amount = 0

            # Change: Make remark empty if the part is completely consumed
            if remaining_in_part == 0:
                new_remarks_parts[i] = ""
            break # Deduction complete
        else:
            # Deduct all of this part and continue to the next
            deducted_amount -= current_part_value
            new_breakdown_parts[i] = "0"

            # Change: Make remark empty if the part is completely consumed
            new_remarks_parts[i] = "" # This part is now 0

    # Filter out parts that became 0 and their corresponding remarks
    combined_parts = []
    for i in range(len(new_breakdown_parts)):
        if new_breakdown_parts[i] != '0':
            combined_parts.append({
                'breakdown': new_breakdown_parts[i],
                'remark': new_remarks_parts[i]
            })

    if not combined_parts:
        final_breakdown_str = "0"
        final_remarks_str = "" # Remarks should be empty if breakdown is 0
    else:
        final_breakdown_str = " | ".join([p['breakdown'] for p in combined_parts])
        final_remarks_str = " | ".join([p['remark'] for p in combined_parts])

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Update the database
        cur.execute(
            sql.SQL("UPDATE inventory_items SET breakdown = %s, remarks = %s WHERE item_code = %s"),
            [final_breakdown_str, final_remarks_str, item_code]
        )
        conn.commit()

        return jsonify({
            "status": "success",
            "message": "Inventory updated successfully.",
            "new_breakdown": final_breakdown_str,
            "new_remarks": final_remarks_str
        })

    except Exception as e:
        print(f"Error updating database: {e}")
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": f"Database error: {e}"}), 500
    finally:
        if conn:
            conn.close()


@app.route('/add_or_update_excel_data', methods=['POST'])
def add_or_update_excel_data():
    data = request.json
    items_from_excel = data.get('items', [])

    if not items_from_excel:
        return jsonify({"status": "error", "message": "No items provided for update."}), 400

    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        updated_count = 0
        added_count = 0

        for item in items_from_excel:
            item_code = item.get('item_code', '').strip()
            breakdown = item.get('breakdown', '')
            remarks = item.get('remarks', '')

            if not item_code:
                continue # Skip items without an item_code

            # Check if item_code already exists
            cur.execute(sql.SQL("SELECT item_code FROM inventory_items WHERE item_code = %s"), [item_code])
            existing_item = cur.fetchone()

            if existing_item:
                # Update existing item
                cur.execute(
                    sql.SQL("UPDATE inventory_items SET breakdown = %s, remarks = %s WHERE item_code = %s"),
                    [breakdown, remarks, item_code]
                )
                updated_count += 1
            else:
                # Add new item
                cur.execute(
                    sql.SQL("INSERT INTO inventory_items (item_code, breakdown, remarks) VALUES (%s, %s, %s)"),
                    [item_code, breakdown, remarks]
                )
                added_count += 1
        conn.commit()
        return jsonify({
            "status": "success",
            "message": f"Excel data processed. Added: {added_count}, Updated: {updated_count}.",
            "added_count": added_count,
            "updated_count": updated_count
        })

    except Exception as e:
        print(f"Error processing Excel data: {e}")
        if conn:
            conn.rollback()
        return jsonify({"status": "error", "message": f"Database error: {e}"}), 500
    finally:
        if conn:
            conn.close()


@app.route('/get_all_inventory', methods=['GET'])
def get_all_inventory():
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(sql.SQL("SELECT item_code, breakdown, remarks FROM inventory_items"))
        items = cur.fetchall()

        inventory_list = []
        for item in items:
            inventory_list.append({
                "item_code": item[0],
                "breakdown": item[1],
                "remarks": item[2]
            })
        return jsonify(inventory_list)
    except Exception as e:
        print(f"Error fetching all inventory: {e}")
        return jsonify({"status": "error", "message": f"Database error: {e}"}), 500
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(debug=True)