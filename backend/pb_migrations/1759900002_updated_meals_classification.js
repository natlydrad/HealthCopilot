/// <reference path="../pb_data/types.d.ts" />

// Migration: Add isFood and categories fields to meals table for classification

migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("meals");

  // Add isFood boolean field (if not exists)
  if (!collection.fields.getByName("isFood")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "bool_isFood",
      "name": "isFood",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "bool"
    }));
  }

  // Add categories JSON array field (if not exists)
  if (!collection.fields.getByName("categories")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "json_categories",
      "maxSize": 2000,
      "name": "categories",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "json"
    }));
  }

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("meals");

  // Remove the fields
  collection.fields.removeById("bool_isFood");
  collection.fields.removeById("json_categories");

  return txApp.save(collection);
});
