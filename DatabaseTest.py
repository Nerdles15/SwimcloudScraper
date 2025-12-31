import psycopg2
from psycopg2 import sql

# Database connection string
CONNECTION_STRING = "postgresql://neondb_owner:npg_KAH3CmQkOb7z@ep-lucky-sound-ahosabgx-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

# Sample data to insert
data = {
    'meet_name': 'NCAA Division I Championship Meet',
    'meet_url': 'https://swimmeetresults.tech/NCAA-Division-I-Men-2025/index.htm',
    'event_number': 1,
    'event_name': 'Men 200 Yard Medley Relay',
    'is_relay': True,
    'team_name': 'Texas',
    'name': 'Modglin, Will SO',
    'order': 1,
    'split': 9.92,
    'leg': 20.32,
    'cumulative': '00:00:20.32'  # interval format as 'HH:MM:SS.MS'
}

try:
    # Connect to the database
    conn = psycopg2.connect(CONNECTION_STRING)
    cursor = conn.cursor()

    # Insert query
    insert_query = sql.SQL("""
                           INSERT INTO "AllResults"
                           (meet_name, meet_url, event_number, event_name, is_relay,
                            "Team Name", "Name", "Order", "Split", "Leg", "Cumulative")
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
                           """)

    # Execute the insert
    cursor.execute(insert_query, (
        data['meet_name'],
        data['meet_url'],
        data['event_number'],
        data['event_name'],
        data['is_relay'],
        data['team_name'],
        data['name'],
        data['order'],
        data['split'],
        data['leg'],
        data['cumulative']
    ))

    # Get the inserted record's id
    inserted_id = cursor.fetchone()[0]

    # Commit the transaction
    conn.commit()

    print(f"✓ Data inserted successfully with ID: {inserted_id}")

except psycopg2.Error as e:
    print(f"✗ Database error: {e}")
    if conn:
        conn.rollback()

except Exception as e:
    print(f"✗ Error: {e}")

finally:
    # Close the connection
    if cursor:
        cursor.close()
    if conn:
        conn.close()
    print("Database connection closed.")