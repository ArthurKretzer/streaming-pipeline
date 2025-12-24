for pod in $(kubectl get pods -n kube-system -l name=ntp-configurator -o name); do 
  echo "Node: $(kubectl get $pod -n kube-system -o jsonpath='{.spec.nodeName}')"
  kubectl exec -n kube-system $pod -- nsenter -t 1 -m -u -n -i -- chronyc tracking | grep -E "Reference ID|System time"
  echo "-----------------------"
done