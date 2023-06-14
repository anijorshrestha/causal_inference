import json
import os
import shutil
import subprocess
from itertools import groupby
from operator import itemgetter
import time
import networkx as nx
import numpy as np
import pydot
import rdflib
from django.shortcuts import render
import pandas as pd
# Create your views here.
import pyAgrum as gum
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.files.storage import FileSystemStorage
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from dowhy import gcm
from dowhy.gcm import fit, auto

from .forms import InterventionForm
from .forms import OWLFileForm
from .models import OWLFile, OWLRelationshipInstance

def view_function(request):
    frame_url = 'api/index1.html'
    return render(request, 'api/live.html', {'frame_url': frame_url})

def home(request):
    return render(request, 'api/home.html', {"owls": OWLFile.objects.all()})


def owl_detail(request, owl_id):
    instance_list = OWLRelationshipInstance.objects.filter(owlfile_id=owl_id)
    ls_dict = []
    print()
    for i in instance_list:
        dict = {
            "id": i.id,
            "is_causal": i.is_causal,
            "instance": i.instance.readable_name,
            "class": i.instance.owl_class.readable_name,
            "relation": i.relationship.query_name,
            "withInstance": i.relation_instance.readable_name,
            "withClass": i.relation_instance.owl_class.readable_name,
        }
        ls_dict.append(dict)

    output_list = []
    class_relation_withClass_instances = {}
    for d in ls_dict:
        key = (d["class"], d["relation"], d["withClass"])
        if key not in class_relation_withClass_instances:
            class_relation_withClass_instances[key] = []
        instance_dict = {k: v for k, v in d.items() if k not in ["class", "relation", "withClass"]}
        class_relation_withClass_instances[key].append(instance_dict)

    for (class_name, relation_name, withClass_name), instances in class_relation_withClass_instances.items():
        output_list.append({
            "class": class_name,
            "relation": relation_name,
            "withClass": withClass_name,
            "instances": instances,
        })

    output_list_grouped_by_relation = []
    relations = set(d["relation"] for d in output_list)
    for relation in relations:
        relation_dicts = [d for d in output_list if d["relation"] == relation]
        grouped_dicts = []
        for class1 in set(d["class"] for d in relation_dicts):
            class1_dicts = [d for d in relation_dicts if d["class"] == class1]
            withClass_dict = {}
            for d in class1_dicts:
                withClass = d["withClass"]
                if withClass not in withClass_dict:
                    withClass_dict[withClass] = []
                withClass_dict[withClass].extend(d["instances"])
            for withClass, instances in withClass_dict.items():
                grouped_dicts.append({
                    "class": class1,
                    "relation": relation,
                    "class2": withClass,
                    "instances": instances,
                })
        output_list_grouped_by_relation.append({
            "relation": relation,
            "grouped_dicts": grouped_dicts,
        })
    obj = get_object_or_404(OWLFile, id=owl_id)
    file = obj.file
    ag = rdflib.Graph()
    ag.parse('media/'+str(file))

    annotation_query = """
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
                PREFIX causality: <http://linkedfactory.org/ontology/causality#>

                SELECT DISTINCT ?objectProperty
                WHERE {
                  ?objectProperty a owl:ObjectProperty ;
                    causality:impliesCausality "true"^^xsd:boolean .
                }

                """

    annotate_qres = ag.query(annotation_query)
    for res in annotate_qres:
        print(res)

    annotate_properties = [str(result[0]).split("#")[-1] if "#" in str(result[0])
                           else str(result[0]).split("/")[-1] for result in annotate_qres]

    # print the list of properties
    print(annotate_properties)

    g = rdflib.Graph()
    g.parse('media/'+str(file))
    knows_query = """
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX owl: <http://www.w3.org/2002/07/owl#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

                SELECT DISTINCT ?property
            WHERE {
              ?property rdf:type owl:ObjectProperty .
              {
                ?property rdf:type owl:IrreflexiveProperty .
              }
              UNION
              {
                ?property rdf:type owl:TransitiveProperty .
              }
            }
            """

    qres = g.query(knows_query)

    properties = [str(result[0]).split("#")[-1] if "#" in str(result[0])
                  else str(result[0]).split("/")[-1] for result in qres]

    possible_causal_list=[]
    non_causal_list=[]
    annotate_causal_list=[]
    for relation in output_list_grouped_by_relation:
        if relation['relation'] in properties:
            possible_causal_list.append(relation)
        else:
            non_causal_list.append(relation)

    for relation in output_list_grouped_by_relation:
        if relation['relation'] in annotate_properties:
            annotate_causal_list.append(relation)

    return render(request, 'api/owl.html', {'owl': get_object_or_404(OWLFile, id=owl_id),'uniquekeys':non_causal_list,'causal_relation':possible_causal_list,'annotated_relation':annotate_causal_list})

@ensure_csrf_cookie
def merge(request,owl_id):
    main_node = (request.POST.get('onN1'))
    branch_node = request.POST.get('onN2')
    triple=request.POST.get('dot_graphN')

    triples=(json.loads(triple))
    filtered_triples = [triple for triple in triples if
                        not ((triple['subject'] == main_node and triple['object'] == branch_node) or
                             (triple['subject'] == branch_node and triple['object'] == main_node))]

    # combine the main node and branch node to form the new node
    new_node = main_node + branch_node

    # replace main_node with new_node if it appears as subject or predicate
    updated_triples = []
    for triple in filtered_triples:
        subject = new_node if triple['subject'] == main_node else triple['subject']
        predicate = triple['predicate']
        obj = new_node if triple['object'] == main_node else triple['object']
        updated_triples.append({'subject': subject, 'predicate': predicate, 'object': obj})

    return render(request, 'api/live.html', {'owl': get_object_or_404(OWLFile, id=owl_id),'triples':updated_triples})


def sparql(request,owl_id):
    query = (request.POST.get('sparqlQuery'))
    print(query)
    obj = get_object_or_404(OWLFile, id=owl_id)
    file = obj.file
    g = rdflib.Graph()
    g.parse('media/' + str(file))

    knows_query = """
                PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
                PREFIX owl: <http://www.w3.org/2002/07/owl#>
                PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
                PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

                    SELECT DISTINCT ?property
                WHERE {
                  ?property rdf:type owl:ObjectProperty .
                  {
                    ?property rdf:type owl:IrreflexiveProperty .
                  }
                  UNION
                  {
                    ?property rdf:type owl:TransitiveProperty .
                  }
                }

                """

    qres = g.query(knows_query)
    properties = [str(result[0]).split("#")[-1] if "#" in str(result[0])
                  else str(result[0]).split("/")[-1] for result in qres]
    print('----sparql------')
    print(properties)
    return render(request, 'api/live.html', {'owl': get_object_or_404(OWLFile, id=owl_id),'value': properties})


def data_detail(request,owl_id):
    data = pd.read_csv('media/'+str(owl_id)+'.csv')
    data_html = data.to_html()
    context = {'loaded_data': data_html}
    return render(request, 'api/data.html', context)

def owl_upload(request, owl_id=None):
    obj = None
    if owl_id:
        obj = get_object_or_404(OWLFile, id=owl_id)
    the_form = OWLFileForm(request.POST or None,
                           instance=obj, files=request.FILES or None)
    if request.method == 'POST' and the_form.is_valid():
        the_owl = the_form.save()
        messages.success(
            request, 'Uploaded!')
        return redirect(owl_detail, owl_id=the_owl.id)
    return render(request, 'api/upload.html', {"form": the_form})

def data_import(request,owl_id):
    if request.method == "POST":
        uploaded_file = request.FILES['document']
        fs= FileSystemStorage()
        fs.save(str(owl_id)+'.csv',uploaded_file)
        return redirect(data_detail,owl_id=owl_id)
    return render(request, 'api/uploaddata.html')

def owl_delete(request, owl_id):
    obj = get_object_or_404(OWLFile, id=owl_id)
    obj.delete()
    return redirect(home)


def owl_download(request, owl_id):
    obj = get_object_or_404(OWLFile, id=owl_id)
    data = obj.download_dag()

    response = HttpResponse(json.dumps(data, indent=4))
    response['Content-Type'] = 'application/json'
    response['Content-Disposition'] = 'attachment; filename=export_' + \
        str(owl_id) + '.json'
    return response


def owl_live(request, owl_id):
    # data = pd.read_csv('media/' + str(owl_id) + '.csv')
    # df = pd.DataFrame(data)
    # data_dict = df.to_dict()
    # data = []
    # for i in range(len(next(iter(data_dict.values())))):
    #     result = ""
    #     for key, value in data_dict.items():
    #         result += f"{key}={value[i]} | "
    #     data.append(result[:-3])
    return render(request, 'api/live.html', {'owl': get_object_or_404(OWLFile, id=owl_id),'intervention':''})

def convert(name):
    # Run owl2vowl.jar converter : convert ontology file TTL to JSON format supported by WebVOWL
    script="java -jar /Users/rojinashrestha/PycharmProjects/djangoProject/api/static/owl2vowl.jar -file /Users/rojinashrestha/PycharmProjects/djangoProject/media/owls/"+name+".owl"
    proc = subprocess.Popen(
        script,
        shell=True, stdout=subprocess.PIPE)
    print("here")
    # Move generated JSON file to data dir
    source = name+'.json'
    destination = '/Users/rojinashrestha/PycharmProjects/djangoProject/api/static/data/YOUR_ONTOLOGY.json'

    if os.path.exists(source):
        print("Exist")
        dest = shutil.move(source, destination)


def owl_visualize(request, owl_id):
    obj = get_object_or_404(OWLFile, id=owl_id)
    file_name=obj.name
    convert(file_name)
    return render(request, 'api/index1.html', {'owl': get_object_or_404(OWLFile, id=owl_id)})

def owl_vis(request):
    return render(request, 'api/index1.html')

@ensure_csrf_cookie
def intervention(request,owl_id):
    outcome_raw = (request.POST.get('OnI'))
    dot = request.POST.get('dot_graphI')
    data = request.POST.get('dataI')
    profile = request.POST.get('profilesI')
    treatment_raw= request.POST.get('onT')

    df = pd.DataFrame(json.loads(data))
    print(data)
    li = list(profile.split(","))
    treatment = str(treatment_raw).strip()
    outcome = str(outcome_raw).strip()
    test=request.POST.get('radiovalue')
    value={treatment:int(test)}
    print(treatment)
    print(outcome)
    print(value)
    prob = OWLFile().intervention(treatment,outcome,value,dot,owl_id,data)
    val=(prob.to_frame())
    transpose=(val.transpose().to_html(classes="striped bordered centered",border="all"))
    return render(request, 'api/live.html', {'owl': get_object_or_404(OWLFile, id=owl_id), 'treatment': treatment,'outcome':outcome,'estimate':transpose,'dataProf':li,'df':data ,'value':test,'intervention':1})



@ensure_csrf_cookie
def counterfactual(request,owl_id):
    start_time = time.time()
    profile = request.POST.get('profile')
    prof = request.POST.get('profilesC')
    li = list(prof.split(","))
    intervening = request.POST.get('onC')
    test = request.POST.get('radiovalueC')
    dot = request.POST.get('dot_graphC')
    data = request.POST.get('dataC')
    df=pd.DataFrame(json.loads(data))
    edges = dot.split(';')
    G = nx.DiGraph()
    for edge in edges[:-1]:
        # Split the edge into its source and target nodes
        source, target = edge.split('->')
        source= source.strip()
        target = target.strip()
        # Add the edge to the graph
        G.add_edge( source, target)
    d = {}
    for item in profile.split(' | '):
        key, value = item.split('=')
        d[key] = [int(value)]
    profiledf = pd.DataFrame(data=d)
    causal_model1 = gcm.InvertibleStructuralCausalModel(G)  # X -> Y -> Z
    auto.assign_causal_mechanisms(causal_model1, df)
    gcm.fit(causal_model1, df)
    sample2 = gcm.counterfactual_samples(
        causal_model1,
        {intervening: lambda x: test},
        observed_data=profiledf)
    end_time = time.time()
    print("Time taken for counterfactual function: {:.2f} seconds".format(end_time - start_time))
    transpose = (sample2.to_html(classes="centered"))
    return render(request, 'api/live.html', {'owl': get_object_or_404(OWLFile, id=owl_id), 'estimate': transpose,'dataProf':li,'df':data,'treatment': intervening,'intervention':0,'profile':profile,'value':test})


def toggle_causality(request, rel_id):
    obj = get_object_or_404(OWLRelationshipInstance, id=rel_id)
    obj.is_causal = not obj.is_causal
    obj.save()
    return HttpResponse()

def testIndep(request,owl_id):
    var1 = request.POST.get('var1')
    var2 = request.POST.get('var2')
    knowing = request.POST.getlist('knowing')
    bn = gum.fastBN("A->B<-C->D->E<-F<-A;C->G<-H<-I->J")
    res="" if bn.isIndependent(var1,var2,knowing) else " NOT"
    giv="." if len(knowing)==0 else f" given {knowing}."
    independence=f"{var1} and {var2} are{res} independent{giv}"
    return render(request, 'api/live.html', {'owl': get_object_or_404(OWLFile, id=owl_id), 'independence': independence,'intervention':0})



