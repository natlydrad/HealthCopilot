/// <reference path="../pb_data/types.d.ts" />
migrate((db) => {
  const dao = new Dao(db);

  // ---- sleep_daily ----
  const sleep = new Collection({
    "name": "sleep_daily",
    "type": "base",
    "schema": [
      { "name": "date", "type": "date", "required": true },
      { "name": "total_min", "type": "number" },
      { "name": "rem_min", "type": "number" },
      { "name": "deep_min", "type": "number" },
      { "name": "core_min", "type": "number" },
      { "name": "inbed_min", "type": "number" },
      { 
        "name": "user",
        "type": "relation",
        "options": { "collectionId": "_pb_users_auth_", "cascadeDelete": true }
      }
    ],
    "indexes": [
      "CREATE UNIQUE INDEX sleep_daily_user_date ON sleep_daily (user, date)"
    ]
  });
  dao.saveCollection(sleep);

  // ... (rest of energy_daily, heart_daily, body_daily same as before)
}, (db) => {
  const dao = new Dao(db);
  for (const name of ["sleep_daily", "energy_daily", "heart_daily", "body_daily"]) {
    const c = dao.findCollectionByNameOrId(name);
    if (c) dao.deleteCollection(c);
  }
});