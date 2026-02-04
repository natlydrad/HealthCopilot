/// <reference path="../pb_data/types.d.ts" />
/**
 * Add core ingredient fields (name, quantity, unit, usdaCode, nutrition, source, rawResponse).
 * These were in pb_migrations_off/1759548130 - without them, PocketBase ignores writes and
 * returns no nutrition. Idempotent: skips fields that already exist.
 */
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  if (!collection.fields.getByName("name")) {
    collection.fields.add(new Field({
      "autogeneratePattern": "",
      "hidden": false,
      "id": "text1579384326",
      "max": 0,
      "min": 0,
      "name": "name",
      "pattern": "",
      "presentable": false,
      "primaryKey": false,
      "required": false,
      "system": false,
      "type": "text"
    }));
  }

  if (!collection.fields.getByName("quantity")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "number2683508278",
      "max": null,
      "min": null,
      "name": "quantity",
      "onlyInt": false,
      "presentable": false,
      "required": false,
      "system": false,
      "type": "number"
    }));
  }

  if (!collection.fields.getByName("unit")) {
    collection.fields.add(new Field({
      "autogeneratePattern": "",
      "hidden": false,
      "id": "text3703245907",
      "max": 0,
      "min": 0,
      "name": "unit",
      "pattern": "",
      "presentable": false,
      "primaryKey": false,
      "required": false,
      "system": false,
      "type": "text"
    }));
  }

  if (!collection.fields.getByName("usdaCode")) {
    collection.fields.add(new Field({
      "autogeneratePattern": "",
      "hidden": false,
      "id": "text2638666016",
      "max": 0,
      "min": 0,
      "name": "usdaCode",
      "pattern": "",
      "presentable": false,
      "primaryKey": false,
      "required": false,
      "system": false,
      "type": "text"
    }));
  }

  if (!collection.fields.getByName("nutrition")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "json3083034865",
      "maxSize": 0,
      "name": "nutrition",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "json"
    }));
  }

  if (!collection.fields.getByName("source")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "select1602912115",
      "maxSelect": 1,
      "name": "source",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "select",
      "values": ["gpt", "usda", "nutritionix", "manual"]
    }));
  }

  if (!collection.fields.getByName("rawResponse")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "json3305188680",
      "maxSize": 0,
      "name": "rawResponse",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "json"
    }));
  }

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");
  try {
    collection.fields.removeById("text1579384326");
  } catch (e) {}
  try {
    collection.fields.removeById("number2683508278");
  } catch (e) {}
  try {
    collection.fields.removeById("text3703245907");
  } catch (e) {}
  try {
    collection.fields.removeById("text2638666016");
  } catch (e) {}
  try {
    collection.fields.removeById("json3083034865");
  } catch (e) {}
  try {
    collection.fields.removeById("select1602912115");
  } catch (e) {}
  try {
    collection.fields.removeById("json3305188680");
  } catch (e) {}
  return txApp.save(collection);
});
