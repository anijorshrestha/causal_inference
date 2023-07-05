import networkx as nx
import owlready2
import pandas as pd
import rdflib
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from owlready2 import get_ontology, onto_path, default_world
import pyAgrum as gum
import pyAgrum.causal as csl


class OWLFile(models.Model):
    name = models.CharField(max_length=256, blank=True, null=True)
    file = models.FileField(upload_to='owls/')
    # META
    timestamp = models.DateTimeField(auto_now_add=True)
    last_change = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ontology"
        verbose_name_plural = 'Ontologies'

    def __str__(self) -> str:
        return self.name

    @property
    def total_class_count(self) -> int:
        return OWLClass.objects.filter(owl=self).count()

    @property
    def total_instance_count(self) -> int:
        return OWLInstance.objects.filter(owl_class__owl=self).count()

    @property
    def total_relation_count(self) -> int:
        return OWLRelationship.objects.filter(owl=self).count()

    def get_classes(self):
        all_classes = []
        for clas in OWLClass.objects.filter(owl=self):
            if len(clas.relationships) > 0:
                all_classes.append(clas)

        return all_classes

    def get_relationships(self):
        return OWLRelationship.objects.filter(owl=self)

    def analyze(self, save=True):
        g = rdflib.Graph()
        g.parse("file://" + self.file.path)
        owl_data = get_ontology("file://" + self.file.path).load()
        #owl_data = get_ontology("media/owls/20230703_ROXANA_v1_var_IOFcausal_inclVarStates_inclMergedDataCL4_allMerged (1).owl").load()
        OWLClass.objects.filter(owl=self).delete()
        OWLRelationship.objects.filter(owl=self).delete()


        # rels = [OWLRelationship(name=rel.iri, owl=self) for rel in owl_data.properties()]
        # OWLRelationship.objects.bulk_create(rels, ignore_conflicts=True)

        all_classes = []
        all_rels =[]
        instance_cache = []
        list_cls=[]
        annotation_query = """
                    PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                    PREFIX owl: <http://www.w3.org/2002/07/owl#>
                    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                    PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

                    SELECT ?Class ?instances
                                     WHERE {
                                       ?Class rdf:type owl:Class .
                                       ?instances rdf:type ?Class .
                                     }

                    """
        annotate_qres = g.query(annotation_query)
        for cls in annotate_qres:
            if 'commissioning' in cls.Class:
                class_iri=cls.Class.split('#')[-1]
            else:
                class_iri = cls.Class.split('/')
            class_label=''
            if class_iri not in list_cls:
                list_cls.append(class_iri)
                all_classes.append(OWLClass(owl=self, name=class_iri, label=class_label))
        OWLClass.objects.bulk_create(all_classes, ignore_conflicts=True)

        list_ins=[]
        all_instance = []
        for i in annotate_qres:
            if 'commissioning' in i.Class:
                class_iri = i.Class.split('#')[-1]
            else:
                class_iri = i.Class.split('/')[-1]
            the_class, _ = OWLClass.objects.get_or_create(name=class_iri, owl=self)

            if 'commissioning' in i.instances:
                instance_iri = i.instances.split('#')[-1]
            else:
                instance_iri = i.instances.split('/')[-1]
            if instance_iri not in list_ins:
                list_ins.append(instance_iri)
                all_instance.append(OWLInstance(name=instance_iri, owl_class=the_class))
        OWLInstance.objects.bulk_create(all_instance, ignore_conflicts=True)


        annotation_query= """
                           PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                           PREFIX owl: <http://www.w3.org/2002/07/owl#>
                           PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                           PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

                           SELECT ?relation
                             WHERE {
                               ?instances ?relation ?instance2 .
                               ?relation rdf:type owl:ObjectProperty .
                             }

                           """
        relations = g.query(annotation_query)
        list_ax=[]
        auxiliaryReList = []
        for rel in relations:
            if 'commissioning' in rel.relation:
                rel_iri = rel.relation.split('/')[-1]
            else:
                rel_iri = rel.relation.split('#')[-1]
            if rel_iri not in list_ax:
                list_ax.append(rel_iri)
                auxiliaryReList.append(OWLRelationship(name=rel_iri, owl=self))

        OWLRelationship.objects.bulk_create(auxiliaryReList, ignore_conflicts=True)


        all_relinstance = []
        relinstance = list(default_world.sparql("""
                                      SELECT DISTINCT ?Instance ?Relation ?Instance2
                                                WHERE { 
                                            ?Instance ?Relation ?Instance2.
                                            ?Relation rdf:type owl:ObjectProperty.
                                            ?Instance rdf:type ?Class.
                                            ?Instance2 rdf:type ?Class2.
                                            ?Class rdf:type owl:Class.
                                            ?Class2 rdf:type owl:Class.
                                            }
                                """))

        for i in relinstance:
            insOne = i[0]
            relation = i[1]
            insTwo =i[2]
            if 'VAR' in str(insOne):
                splitOne = str(insOne).split('VAR.')
            else:
                splitOne = str(insOne).split('roxana.')
            insOne_iri = splitOne[-1]
            the_insOne, _ = OWLInstance.objects.get_or_create(name=insOne_iri)

            if 'VAR' in str(relation):
                splitIn = str(relation).split('VAR.')
            else:
                splitIn = str(relation).split('roxana.')
            realtion_iri = splitIn[-1]
            the_relation, _ = OWLRelationship.objects.get_or_create(name=realtion_iri, owl=self)

            if 'VAR' in str(insTwo):
                splitTwo = str(insTwo).split('VAR.')
            else:
                splitTwo = str(insTwo).split('roxana.')
            insTwo_iri = splitTwo[-1]
            the_insTwo, _ = OWLInstance.objects.get_or_create(name=insTwo_iri)

            all_relinstance.append(OWLRelationshipInstance(
                                 owlfile=self,
                                 instance=the_insOne,
                                 relationship=the_relation,
                                 relation_instance=the_insTwo
                             ))
        OWLRelationshipInstance.objects.bulk_create(all_relinstance, ignore_conflicts=True)

        if save:
            self.save()

    def triple(self):
        G = nx.DiGraph()
        nodes = []
        for the_node in self.get_causal_classes():
            G.add_node(the_node.readable_name)
            nodes.append(the_node.readable_name)
        edges = []
        triples = []
        for rel in self.get_causal_relationships():
            G.add_edge(rel.instance.owl_class.readable_name,
                       rel.relation_instance.owl_class.readable_name, weight=1)
            edge_labels = {
                "subject": rel.instance.owl_class.readable_name, "predicate": rel.relationship.query_name,
                "object": rel.relation_instance.owl_class.readable_name}

            edges.append((rel.instance.owl_class.readable_name, rel.relation_instance.owl_class.readable_name))
            triples.append(edge_labels)

        unique_dicts = [dict(s) for s in set(frozenset(d.items()) for d in triples)]
        print(unique_dicts)
        return unique_dicts

    def download_dag(self):
        return nx.node_link_data(self.gen_dag())

    def generate_cy(self):
        G, edges ,nodes= self.gen_dag()
        print(edges)

        if (nx.is_directed_acyclic_graph(G)) is False:
            return json.dumps({'data':'False'})
        else:
            new_jon = nx.cytoscape_data(G)
            interactive=json.dumps(new_jon)
            return interactive

    def get_causal_classes(self):
        classes = []
        for the_class in self.get_classes():
            if the_class.causal_relationships:
                classes.append(the_class)
        return classes

    def get_causal_instances(self):
        instances = []
        for the_instance in OWLInstance.objects.filter(owl_class__owl=self):
            if len(the_instance.causal_relationships):
                instances.append(the_instance)
        return instances

    def get_causal_relationships(self):
        return OWLRelationshipInstance.objects.filter(relationship__owl=self, is_causal=True)

    def intervention(self,doing,on,values_dict,dot,file,data):
        df=pd.DataFrame(json.loads(data))
        bn = gum.fastBN(dot)
        # data = pd.DataFrame(np.array([[1, 0, 1],
        #                               [1, 0, 1],
        #                               [1, 0, 1],
        #                               [1, 0, 1],
        #                               [1, 0, 1],
        #                               [1, 0, 1],
        #                               [0, 1, 0],
        #                               [0, 1, 0],
        #                               [0, 1, 0],
        #                               [0, 1, 0],
        #                               [0, 1, 0],
        #                               [0, 1, 0]
        #                               ]),
        #                     columns=['C L4.13', 'C L4.14', 'Clamp D02- X1:9 Stasis'])
        learner = gum.BNLearner(df, bn)
        learner.useAprioriSmoothing(10)
        bn3 = learner.learnParameters(bn.dag())
        d = csl.CausalModel(bn3)
        causalFormula, computation, explanation = csl.causalImpact(d, doing=doing, on=on, values=values_dict)
        print(computation)
        print(explanation)
        prob=(computation.topandas())
        end_time = time.time()

        return prob

@receiver(post_save, sender=OWLFile)
def run_analysis(sender, instance, created, **kwargs):
    if created:
        instance.analyze()


def resolve_camel_case(input_str) -> str:
    i = 0
    output = ""
    while (i < len(input_str)):
        if (ord(input_str[i]) >= ord('A') and ord(input_str[i]) <= ord('Z')):
            output += " " + input_str[i]
        else:
            output += input_str[i]
        i += 1
    return output.strip()


class OWLInstance(models.Model):
    owl_class = models.ForeignKey('api.OWLClass', on_delete=models.CASCADE)
    name = models.CharField(max_length=256)

    @property
    def readable_name(self) -> str:
        if 'BFO' in self.name or 'CommonCoreOntologies' in self.name:
            return resolve_camel_case(self.name.split('/')[-1])
        return resolve_camel_case(self.name.split('#')[-1])

    @property
    def relationships(self):
        return OWLRelationshipInstance.objects.filter(instance=self) | OWLRelationshipInstance.objects.filter(
            relation_instance=self)

    @property
    def causal_relationships(self):
        return OWLRelationshipInstance.objects.filter(instance=self,
                                                      is_causal=True) | OWLRelationshipInstance.objects.filter(
            relation_instance=self, is_causal=True)

    def __str__(self) -> str:
        return self.readable_name

    class Meta:
        verbose_name = "Instance"
        verbose_name_plural = 'Instances'
        unique_together = ["owl_class", "name"]


class OWLClass(models.Model):
    owl = models.ForeignKey('api.OWLFile', on_delete=models.CASCADE)
    name = models.CharField(max_length=1024)
    label = models.CharField(max_length=1024, null=True, blank=True)

    def __str__(self) -> str:
        return self.readable_name

    @property
    def readable_name(self) -> str:
        #if self.label:
            #return self.label
        if 'BFO' in self.name or 'CommonCoreOntologies' in self.name:
            return resolve_camel_case(self.name.split('/')[-1])
        return resolve_camel_case(self.name.split('#')[-1])

    @property
    def instances(self):
        return OWLInstance.objects.filter(owl_class=self)

    @property
    def relationships(self):
        all_rel = OWLRelationshipInstance.objects.none()
        for inc in self.instances:
            all_rel = all_rel | inc.relationships
        return all_rel

    @property
    def causal_relationships(self) -> bool:
        for rel in self.relationships:
            if rel.is_causal:
                return True
        return False

    @property
    def relationship_classes(self):
        all_class = []
        for rel in self.relationships:
            if rel.is_causal:
                all_class.append(rel.instance.owl_class)
        return all_class

    class Meta:
        verbose_name = "Class"
        verbose_name_plural = 'Classes'
        unique_together = ["owl", "name"]


class OWLRelationship(models.Model):
    name = models.CharField(max_length=256)
    owl = models.ForeignKey('api.OWLFile', on_delete=models.CASCADE)

    def __str__(self) -> str:
        return self.query_name

    @property
    def query_name(self) -> str:
        #print(self.name)
        if '#' in self.name:
            return self.name.split("#")[-1]
        # if '.' in self.name:
        #     return self.name.split(".")[-2]
        if '/' in self.name:
            return self.name.split("/")[-1]
        return self.name

    class Meta:
        verbose_name = "Relationship"
        verbose_name_plural = 'Relationships'


class OWLRelationshipInstance(models.Model):
    owlfile = models.ForeignKey(
        'api.OWLFile', on_delete=models.CASCADE)
    relationship = models.ForeignKey(
        'api.OWLRelationship', on_delete=models.CASCADE)
    instance = models.ForeignKey(
        'api.OWLInstance', on_delete=models.CASCADE, related_name="the_instance")
    is_causal = models.BooleanField(default=False)
    relation_instance = models.ForeignKey(
        'api.OWLInstance', on_delete=models.CASCADE, related_name="relation_instance")

    @property
    def owl(self):
        return self.relationship.owl

    @property
    def in_classes(self):
        return OWLInstance.objects.filter(self)

    class Meta:
        verbose_name = "Relationship Instance"
        verbose_name_plural = 'Relationship Instances'




