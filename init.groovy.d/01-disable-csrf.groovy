import jenkins.model.*

def instance = Jenkins.get()
if (instance != null) {
    instance.crumbIssuer = null
    instance.save()
    println "CSRF protection fully disabled via init script"
}