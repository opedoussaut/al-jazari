from rdflib import Namespace

JZ = Namespace("https://w3id.org/jazari/ontology#")
JZR = Namespace("https://w3id.org/jazari/kg/")
CORA = Namespace("http://purl.org/ieee1872-owl/cora-bare#")
CORAX = Namespace("http://purl.org/ieee1872-owl/corax#")
RPARTS = Namespace("http://purl.org/ieee1872-owl/rparts#")
SUMO = Namespace("http://purl.org/ieee1872-owl/sumo-cora#")
POS_NS = Namespace("http://purl.org/ieee1872-owl/pos#")
IEEEANN = Namespace("http://purl.org/ieee1872-owl/annotation#")
QUDT = Namespace("http://qudt.org/schema/qudt/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
PROV = Namespace("http://www.w3.org/ns/prov#")
SOSA = Namespace("http://www.w3.org/ns/sosa/")

PREFIXES = {
    "jz": JZ, "jzr": JZR, "cora": CORA, "corax": CORAX, "rparts": RPARTS, "sumo": SUMO,
    "qudt": QUDT, "unit": UNIT, "prov": PROV, "sosa": SOSA, "ieee": IEEEANN,
}


def sparql_prefixes() -> str:
    base = {
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
        "owl": "http://www.w3.org/2002/07/owl#",
        "skos": "http://www.w3.org/2004/02/skos/core#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
    }
    base.update({k: str(v) for k, v in PREFIXES.items()})
    return "\n".join(f"PREFIX {k}: <{v}>" for k, v in base.items()) + "\n"
