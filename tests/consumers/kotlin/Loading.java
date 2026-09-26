import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public class Loading {
    public static void main(String[] args) throws Exception {
        List<URL> urls = new ArrayList<>();
        try (Stream<Path> files = Files.list(Paths.get(args[0]))) {
            for (Path file : (Iterable<Path>) files.filter(path -> path.toString().endsWith(".jar"))::iterator) {
                urls.add(file.toUri().toURL());
            }
        }
        URL[] classpath = urls.toArray(new URL[0]);
        try (URLClassLoader first = new URLClassLoader(classpath, null);
             URLClassLoader second = new URLClassLoader(classpath, null)) {
            Class<?> firstFacade = Class.forName("ai.arboresce.Arboresce", true, first);
            Class<?> secondFacade = Class.forName("ai.arboresce.Arboresce", true, second);
            if (firstFacade == secondFacade || firstFacade.getClassLoader() == secondFacade.getClassLoader()) {
                throw new AssertionError("The consumer requires two independent classloaders");
            }
            for (Class<?> facade : new Class<?>[] {firstFacade, secondFacade}) {
                if (!"Arboresce".equals(facade.getMethod("name").invoke(null))) {
                    throw new AssertionError("Native call from isolated classloader");
                }
            }
        }
    }
}
