/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // update collection data
  unmarshal({
    "createRule": "@request.auth.id = true"
  }, collection)

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // update collection data
  unmarshal({
    "createRule": "@request.auth.id = mealId.user\n"
  }, collection)

  return app.save(collection)
})
