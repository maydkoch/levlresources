from openai import OpenAI
from neo4j import GraphDatabase
import json
import sys
from datetime import datetime

#configuration. I store my API key as an environment variable. 

#openai.api_key = ""
neo4j_uri = "bolt://localhost:7687"
neo4j_user = "neo4j"
neo4j_password = "password"

driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))


def extract_graph_from_text(text):
    prompt = f"""
You are make a knowledge graph relating modalities (habits, supplements, exercises, routines, etc),
observeable benefits (increased muscle gain, improved endurance etc), 
observable negatives (increased risk of cardiovascular disease, cancer, etc),
and sources (scientific sources with evidence)

Given the following text, return a JSON object with "nodes" and "relationships".

Each node should have:
- "name": the unique identifier of the entity
- "label": Either "Modality", "Benefit", "Negative", or "Source"
- "description": a short description

Modalities should have more information than the other types of nodes. The current information we keep track of is:
- "subtype": the subcategory of modality. the categories are: Exercise, Supplement, Mindfulness, Environmental, Food, Sleep, and Emotional. Pick the category that most closely aligns with the modality in question.
- "effort_score": a value ranging from 1-100 that describes the amount of effort required in order to participate in a modality
- "dosage_lowbound": the lower bound for dosage of the modality, if applicable, represented as an integer
- "dosage_upbound": the upper bound for dosage of the modality, if applicable, represented as an integer
- "dosage_units": the units the dosage represents. This could be mg, mcg, minutes, etc
- "frequency_min": the minimum amount of times the modality should be done per repeat period, if applicable, represented as an integer
- "frequency_max": the maximum amount of times the modality should be done per repeat period, if applicable, represented as an integer
- "repeat": how often the modality should be repeated at the given frequency, e.g. daily, weekly, monthly, or as needed
- "prescription_or_administered": a boolean value displaying whether or not something is a prescribed treatment or administered by a health professional

Additionally, source nodes should store:
- "doi": the doi link of the scientific source, if it can be found

Each relationship should have:
- "source": name of the source node
- "target": name of the target node
- "type": the type of relationship, which should be used as the label
    - for modality-to-source links (when a modality is studied in a source), the label should be "STUDIED_IN"
    - for source-to-benefit or source-to-negative links (when a study shows results pointing to an outcome), the label should be "POINTS_TO"
    - for modality-to-modality links (when modalities are beneficial to each other or conflict), the label should be either "SYNERGISTIC" or "ANTAGONISTIC" depending on context, and should go both ways (doubly linked)
- "explanation": a sentence explaining the relationship
- "effect_size": a number from 1-100 representing the magnitude of the relationship 
- "confidence": a number from 1-100 representing the certainty of the science
- "conditions": if applicable, describe any applicable conditions for this relationship (e.g 'in men 65 and older' or 'if used excessively')

Only one modality should be linked to any given source node. if there is a study that goes over two different modalities, break it up into
two different source nodes and label them accordingly. confidence and effect size values should be PER MODALITY, with the study giving
them their values.

If you cannot find any of the information listed above, leave it as null. Under no circumstances should you extrapolate or fabricate data.

For the given piece of literature, create a source node and either create a modality node for the modality being studied, or use an existing node
of the same or nearly identical name. Preference should be given to linking an applicable node instead of creating a new one when possible. 
Link the modality node to the source node. Then, link all applicable benefits or negatives to the source node,with corresponding 
magnitude and confidence scores. Create benefit and negative nodes if needed, but preferably use existing ones.

Return only valid JSON, nothing else. Here is the text:

\"\"\"{text}\"\"\"
"""

    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format = {"type": "json_object"}
    )

    json_str = response.choices[0].message.content

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Strip ```json if present
        cleaned = json_str.strip().strip("```json").strip("```")
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            print("PROGRAM ERROR: Can't read JSON")
            sys.exit()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"res_log/res_{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    print(f"Graph generated, saved as {filename}")
    return data



def node_exists(tx, name, label):
    result = tx.run(f"MATCH (n:{label} {{name: $name}}) RETURN count(n) AS count", name=name)
    return result.single()["count"] > 0

def create_node(tx, name, label, description, subtype, effort_score, dosage_lowbound, dosage_upbound, dosage_units, frequency_min, frequency_max, repeat, prescribed_or_administered):
    query = f"""
    MERGE (n:$label{{n.name=$name}})
    SET n.description = $description, 
        n.subtype = $subtype,
        n.effort_score=$effort_score,
        n.dosage_lowbound=$dosage_lowbound,
        n.dosage_upbound=$dosage_upbound,
        n.dosage_units=$dosage_units,
        n.frequency_min=$frequency_min,
        n.frequency_max=$frequency_max,
        n.repeat=$repeat,
        n.prescribed_or_administered=$prescribed_or_administered
    """
    tx.run(query, name=name, label=label, description=description, subtype=subtype, effort_score=effort_score, dosage_lowbound=dosage_lowbound, 
           dosage_upbound=dosage_upbound, dosage_units=dosage_units, frequency_min=frequency_min, frequency_max=frequency_max, repeat=repeat, prescribed_or_administered=prescribed_or_administered)


def create_relationship(tx, source, target, rel_type, explanation, effect_size, confidence, conditions):
    safe_type = rel_type.upper().replace(" ", "_").replace("-", "_")
    query = f"""
    MATCH (a {{name: $source}}), (b {{name: $target}})
    MERGE (a)-[r:{safe_type}]->(b)
    SET r.explanation = $explanation, 
        r.effect_size=$effect_size,
        r.confidence=$confidence,
        r.conditions=$conditions
    """
    tx.run(query, source=source, target=target, explanation=explanation,
           effect_size=effect_size, confidence=confidence, conditions=conditions)



def process_graph(graph, literature):
    nodes = graph.get("nodes", [])
    relationships = graph.get("relationships", [])
    with driver.session() as session:
        for node in nodes:
            name = node["name"]
            description = node.get("description", "")
            label = node.get("label", "")
            exists = session.execute_read(node_exists, name, label)
            if not exists:
                session.execute_write(create_node, name, label, description)

        for rel in relationships:
            session.execute_write(
                create_relationship,
                rel["source"],
                rel["target"],
                rel["type"],
                rel["explanation"],
                rel["effect_size"],
                rel["confidence"],
                rel["conditions"]
            )

    print("Graph data successfully processed.")


#for handling long text
def split_text_into_chunks(text, max_words=5000):
    words = text.split()
    return [' '.join(words[i:i + max_words]) for i in range(0, len(words), max_words)]


def get_literature(file):
    with open(file,'r', encoding='utf8') as f:
        list = f.readlines()
        literature = list[0]
        text = ''.join(list[1:]).strip()
    print(f"Analyzing {literature.strip()}...")
    return literature, text
        


if __name__ == "__main__":
    #Parse into literature and content
    literature, text = get_literature(sys.argv[1])

    # Split text into chunks if needed
    chunks = split_text_into_chunks(text)

    print(f"Processing {len(chunks)} chunk(s) of text...")

    for idx, chunk in enumerate(chunks, start=1):
        print(f"\n--- Extracting graph for chunk {idx} ---")
        graph = extract_graph_from_text(chunk)
        process_graph(graph, f"{literature} (Part {idx})")