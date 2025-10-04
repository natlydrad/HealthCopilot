/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // update collection data
  unmarshal({
    "createRule": "1=1",
    "deleteRule": "1=1",
    "listRule": "1=1",
    "updateRule": "1=1",
    "viewRule": "1=1"
  }, collection)

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // update collection data
  unmarshal({
    "createRule": "@request.auth.id = mealId.user\n",
    "deleteRule": "@request.auth.id = mealId.user\n",
    "listRule": "@request.auth.id = mealId.user\n",
    "updateRule": "@request.auth.id = mealId.user\n",
    "viewRule": "@request.auth.id = mealId.user\n"
  }, collection)

  return app.save(collection)
})
