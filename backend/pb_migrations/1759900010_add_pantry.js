/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("user_food_profile");
  if (!collection) return;

  if (!collection.fields.getByName("pantry")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "json_pantry",
      "maxSize": 0,
      "name": "pantry",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "json"
    }));
  }

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("user_food_profile");
  if (!collection) return;
  const field = collection.fields.getByName("pantry");
  if (field) {
    collection.fields.removeById(field.id);
  }
  return txApp.save(collection);
});
