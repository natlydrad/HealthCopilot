/// <reference path="../pb_data/types.d.ts" />

// Migration: Add isFood and categories fields to meals table for classification

migrate((db) => {
  const dao = new Dao(db);
  const collection = dao.findCollectionByNameOrId("meals");

  // Add isFood boolean field
  collection.fields.push({
    "hidden": false,
    "id": "bool_isFood",
    "name": "isFood",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "bool"
  });

  // Add categories JSON array field
  collection.fields.push({
    "hidden": false,
    "id": "json_categories",
    "maxSize": 2000,
    "name": "categories",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "json"
  });

  return dao.saveCollection(collection);
}, (db) => {
  const dao = new Dao(db);
  const collection = dao.findCollectionByNameOrId("meals");

  // Remove the fields
  collection.fields = collection.fields.filter(f => 
    f.name !== "isFood" && f.name !== "categories"
  );

  return dao.saveCollection(collection);
});
