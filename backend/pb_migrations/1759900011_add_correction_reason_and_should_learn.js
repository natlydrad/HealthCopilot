/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("ingredient_corrections");
  if (!collection) return;

  if (!collection.fields.getByName("correctionReason")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "text_correction_reason",
      "max": 0,
      "min": 0,
      "name": "correctionReason",
      "pattern": "",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "text"
    }));
  }
  if (!collection.fields.getByName("shouldLearn")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "bool_should_learn",
      "name": "shouldLearn",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "bool"
    }));
  }

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("ingredient_corrections");
  if (!collection) return;
  const reasonField = collection.fields.getByName("correctionReason");
  if (reasonField) collection.fields.removeById(reasonField.id);
  const learnField = collection.fields.getByName("shouldLearn");
  if (learnField) collection.fields.removeById(learnField.id);
  return txApp.save(collection);
});
