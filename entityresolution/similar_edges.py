# pip3 install neo4j-driver
# python3 example.py

from neo4j import GraphDatabase, basic_auth

URI = "neo4j+ssc://1b551888.databases.neo4j.io"
AUTH = ("neo4j", "MU_rxscxE2q4BSFgP3Fj5MjnAJtvRLL_hlPbfQH5uZI")
driver = GraphDatabase.driver(URI, auth=AUTH)

cypher_query = '''
MATCH (source1)-[a]->(target1)
MATCH (source2)-[b]->(target2)
// not the same user
WHERE a <> b

// compute different similiarities
WITH *,
toInteger(apoc.text.sorensenDiceSimilarity(a.explanation, b.explanation) * 100) AS explanationSimilarity,
toInteger(apoc.text.sorensenDiceSimilarity(type(a), type(b)) * 100) AS typeSimilarity,
toInteger(apoc.text.sorensenDiceSimilarity(source1.name, source2.name) * 100) AS sourceSimilarity,
toInteger(apoc.text.sorensenDiceSimilarity(target1.name, target2.name) * 100) AS targetSimilarity

// compute a total similarity score
WITH a, b, toInteger((explanationSimilarity * 0.2) + (typeSimilarity * 0.2) + (sourceSimilarity * 0.3) + (targetSimilarity * 0.3)) AS similarity

// filter
WHERE similarity >= 90

RETURN type(a), a.explanation, a.literature, type(b), b.explanation, b.literature, similarity

ORDER BY similarity DESC
'''

with driver.session() as session:
  result = session.run(cypher_query)
  records = [dict(record) for record in result]
  print(records)

driver.close()
