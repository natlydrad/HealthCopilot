/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_ing_corrections");

  // Add context (JSON) for conversation history, learned, via, etc.
  if (!collection.fields.getByName("context")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "json_context",
      "maxSize": 0,
      "name": "context",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "json"
    }));
  }

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_ing_corrections");
  const field = collection.fields.getByName("context");
  if (field) {
    collection.fields.removeById(field.id);
  }
  return txApp.save(collection);
});
