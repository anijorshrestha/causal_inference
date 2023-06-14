import base64
import io
import json
import urllib.parse
import time
from array import array


import networkx as nx
import pandas as pd
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from owlready2 import get_ontology, onto_path
import pyAgrum as gum
import pyAgrum.causal as csl
import pandas as pd

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
        owl_data = get_ontology("file://" + self.file.path).load(only_local=True)
        OWLClass.objects.filter(owl=self).delete()
        OWLRelationship.objects.filter(owl=self).delete()

        rels = [OWLRelationship(name=rel.iri, owl=self) for rel in owl_data.properties()]
        OWLRelationship.objects.bulk_create(rels, ignore_conflicts=True)

        all_classes = []
        instance_cache = []

        for cls in list(owl_data.classes()):
            class_iri = cls.iri
            class_label = str(cls.label[0]) if cls.label else None

            all_classes.append(OWLClass(owl=self, name=class_iri, label=class_label))

            # Get all subclasses
            for sub_cls in cls.subclasses():
                all_classes.append(
                    OWLClass(owl=self, name=sub_cls.iri, label=str(sub_cls.label[0]) if sub_cls.label else None))

            for individual in cls.instances():
                for obj_property in list(owl_data.object_properties()):
                    for obj_prop_rel in obj_property[individual]:
                        the_ind, _ = OWLClass.objects.get_or_create(name=class_iri, owl=self)
                        ob = obj_prop_rel.is_a[0]
                        the_rel, _ = OWLClass.objects.get_or_create(name=ob.iri, owl=self)
                        instance_cache.append(OWLRelationshipInstance(
                            owlfile=self,
                            instance=OWLInstance.objects.get_or_create(name=individual.iri, owl_class=the_ind)[0],
                            relationship=OWLRelationship.objects.get(name=obj_property.iri, owl=self),
                            relation_instance=
                            OWLInstance.objects.get_or_create(name=obj_prop_rel.iri, owl_class=the_rel)[0]
                        ))

            for sub_cls in cls.subclasses():
                for individual in sub_cls.instances():
                    for obj_property in list(owl_data.object_properties()):
                        for obj_prop_rel in obj_property[individual]:
                            the_ind, _ = OWLClass.objects.get_or_create(name=sub_cls.iri, owl=self)
                            ob = obj_prop_rel.is_a[0]
                            the_rel, _ = OWLClass.objects.get_or_create(name=ob.iri, owl=self)
                            instance_cache.append(OWLRelationshipInstance(
                                owlfile=self,
                                instance=OWLInstance.objects.get_or_create(name=individual.iri, owl_class=the_ind)[0],
                                relationship=OWLRelationship.objects.get(name=obj_property.iri, owl=self),
                                relation_instance=
                                OWLInstance.objects.get_or_create(name=obj_prop_rel.iri, owl_class=the_rel)[0]
                            ))

        OWLClass.objects.bulk_create(all_classes, ignore_conflicts=True)
        OWLRelationshipInstance.objects.bulk_create(instance_cache)

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




