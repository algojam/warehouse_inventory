const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const app = express();
const PORT = 3000;

// Connect to SQLite database
const db = new sqlite3.Database('./inventory.db', (err) => {
    if (err) {
        console.error('Error connecting to database:', err.message);
    } else {
        console.log('Connected to the SQLite database.');
        // Create table if it doesn't exist
        // ***** BINAGO ANG TABLE SCHEMA DITO PARA SA JSON STRINGS *****
        db.run(`CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE, -- Changed to 'code' from 'item_code' for consistency with frontend, and added UNIQUE
            count_json TEXT,          -- Store count array as JSON string
            remarks_json TEXT         -- Store remarks array as JSON string
        )`, (createErr) => {
            if (createErr) {
                console.error('Error creating table:', createErr.message);
            } else {
                console.log('Items table created or already exists with updated schema.');
            }
        });
    }
});

// Middleware to parse JSON bodies
app.use(express.json());
// Serve static files (your HTML, CSS, JS) from the current directory
app.use(express.static(__dirname));

// --- API Endpoints ---

// Get all inventory items
app.get('/api/items', (req, res) => {
    // Select all columns, including the JSON strings
    db.all('SELECT id, code, count_json, remarks_json FROM items', [], (err, rows) => {
        if (err) {
            res.status(500).json({ error: err.message });
            return;
        }
        // Parse JSON strings back to arrays before sending to frontend
        const items = rows.map(row => ({
            id: row.id,
            code: row.code,
            count: row.count_json ? JSON.parse(row.count_json) : [],
            remarks: row.remarks_json ? JSON.parse(row.remarks_json) : []
        }));
        res.json(items);
    });
});

// Add a new inventory item
app.post('/api/items', (req, res) => {
    const { code, count, remarks } = req.body; // Using 'code' consistent with frontend

    if (!code) {
        return res.status(400).json({ success: false, message: 'Item code is required.' });
    }

    // Convert arrays to JSON strings for storage
    const countJson = JSON.stringify(Array.isArray(count) ? count : []);
    const remarksJson = JSON.stringify(Array.isArray(remarks) ? remarks : []);

    const sql = 'INSERT INTO items (code, count_json, remarks_json) VALUES (?, ?, ?)';
    db.run(sql, [code, countJson, remarksJson], function(err) {
        if (err) {
            if (err.message.includes('UNIQUE constraint failed: items.code')) {
                return res.status(409).json({ success: false, message: 'Item code already exists.' });
            }
            res.status(500).json({ success: false, message: err.message });
            return;
        }
        res.status(201).json({ success: true, message: 'Item added successfully!', id: this.lastID, code: code, count: count, remarks: remarks });
    });
});

// Update an existing inventory item
app.put('/api/items/:id', (req, res) => {
    const { id } = req.params;
    const { code, count, remarks } = req.body;

    if (!code) {
        return res.status(400).json({ success: false, message: 'Item code is required.' });
    }

    const countJson = JSON.stringify(Array.isArray(count) ? count : []);
    const remarksJson = JSON.stringify(Array.isArray(remarks) ? remarks : []);

    const sql = 'UPDATE items SET code = ?, count_json = ?, remarks_json = ? WHERE id = ?';
    db.run(sql, [code, countJson, remarksJson, id], function(err) {
        if (err) {
            if (err.message.includes('UNIQUE constraint failed: items.code')) {
                return res.status(409).json({ success: false, message: 'Item code already exists.' });
            }
            res.status(500).json({ success: false, message: err.message });
            return;
        }
        if (this.changes === 0) {
            return res.status(404).json({ success: false, message: 'Item not found.' });
        }
        res.json({ success: true, message: 'Item updated successfully!' });
    });
});

// Delete an inventory item
app.delete('/api/items/:id', (req, res) => {
    const { id } = req.params;

    const sql = 'DELETE FROM items WHERE id = ?';
    db.run(sql, id, function(err) {
        if (err) {
            res.status(500).json({ success: false, message: err.message });
            return;
        }
        if (this.changes === 0) {
            return res.status(404).json({ success: false, message: 'Item not found.' });
        }
        res.json({ success: true, message: 'Item deleted successfully!' });
    });
});


// Start the server
app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
    console.log(`Open your browser and go to http://localhost:${PORT}/1.html`); // Note: Changed to 1.html
});

// Close the database connection when the app closes
process.on('SIGINT', () => {
    db.close((err) => {
        if (err) {
            console.error(err.message);
        }
        console.log('Database connection closed.');
        process.exit(0);
    });
});