/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
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
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // update collection data
  unmarshal({
    "createRule": null,
    "deleteRule": null,
    "listRule": null,
    "updateRule": null,
    "viewRule": null
  }, collection)

  return app.save(collection)
})
